// RH_PrepWIPForShadow.jsx
// Prepares layered WIP PSDs as the product input for the Weave shadow workflow.
// For each WIP file it:
//   1. opens the PSD (the WIP file itself is never saved or modified)
//   2. turns off the Shadow group(s)
//   3. measures the product's bounding box (from the "Main" group; falls back to
//      the white background if there is no usable Main group)
//   4. crops / expands the canvas to a 3:2 frame with PADDING around the product
//   5. flattens, converts to RGB 8-bit, and resizes to LONG_EDGE_PX on the long side
//   6. saves <name>.jpg to ~/Desktop/RH_ShadowPrep
// The frame is worked out per file from the product's size, so WIPs can be any canvas
// size. Each crop is logged to RH_ShadowPrep_log.csv in the output folder, so the
// cast shadow can later be placed back into the WIP at the right scale and position.
// Save as .jsx, run via File > Scripts > Browse, then pick the WIP files.

#target photoshop

(function () {
    // === CONFIGURABLE PARAMETERS ===

    // Space on every side of the product, as a fraction of the product's LONGER side.
    // 0.37 matches the reference image (about 37% each side). Higher = more white space.
    var PADDING = 0.37;

    // Output frame aspect ratio (width : height) and size of its long side in pixels
    var ASPECT_W = 3;
    var ASPECT_H = 2;
    var LONG_EDGE_PX = 4000;

    // The group (folder) that holds the product and its mask. Its visible pixels are
    // used to measure how the product sits in the canvas.
    var MAIN_GROUP_PATTERN = /^main$/i;

    // Any group (folder) whose name matches this is turned off.
    // Default: name contains "shadow", case-insensitive ("Shadow", "SHADOWS", "Cast Shadow"...)
    var SHADOW_GROUP_PATTERN = /shadow/i;

    // Fallback measurement only (used when there is no usable Main group): pixels at or
    // above this level (0-255) count as white background. Lower it if faint haze around
    // the product is throwing the bounds off.
    var WHITE_POINT = 250;

    // Where the WIP files are. Leave "" to be asked each run (multi-select),
    // or set a folder, e.g. "~/Desktop/WIP", to process every PSD/PSB in it.
    var INPUT_FOLDER = "";

    // === SAVE PARAMETERS ===
    var OUTPUT_FOLDER = "~/Desktop/RH_ShadowPrep";
    var OUTPUT_SUFFIX = "";      // added to the filename, e.g. "_prep" gives chair_prep.jpg
    var JPEG_QUALITY = 12;       // 1-12 (12 = highest)

    var LOG_NAME = "RH_ShadowPrep_log.csv";
    var ASPECT = ASPECT_W / ASPECT_H;

    // ---------------------------------------------------------------------------

    function pickFiles() {
        if (INPUT_FOLDER !== "") {
            var folder = new Folder(INPUT_FOLDER);
            if (!folder.exists) {
                alert("INPUT_FOLDER does not exist:\n" + INPUT_FOLDER);
                return null;
            }
            return folder.getFiles(function (f) {
                return (f instanceof File) && /\.(psd|psb)$/i.test(f.name);
            });
        }
        var isWin = $.os.indexOf("Windows") !== -1;
        var filter = isWin ? "Photoshop files:*.psd;*.psb" : function (f) {
            return (f instanceof Folder) || /\.(psd|psb)$/i.test(f.name);
        };
        var picked = File.openDialog("Select the WIP PSD files to prepare", filter, true);
        if (!picked) {
            return null;
        }
        if (picked instanceof File) {
            picked = [picked];
        }
        return picked;
    }

    // Returns the already-open document for this file, or null
    function findOpenDoc(file) {
        for (var i = 0; i < app.documents.length; i++) {
            try {
                if (app.documents[i].fullName.fsName === file.fsName) {
                    return app.documents[i];
                }
            } catch (e) {
                // unsaved documents have no fullName
            }
        }
        return null;
    }

    // Turns off every group whose name matches SHADOW_GROUP_PATTERN (searches nested groups)
    function hideShadowGroups(container, hiddenNames) {
        for (var i = 0; i < container.layers.length; i++) {
            var lyr = container.layers[i];
            if (lyr.typename === "LayerSet") {
                if (SHADOW_GROUP_PATTERN.test(lyr.name)) {
                    lyr.visible = false;
                    hiddenNames.push(lyr.name);
                } else {
                    hideShadowGroups(lyr, hiddenNames);
                }
            }
        }
    }

    // Index path (e.g. [2] or [0, 3]) to the first group matching pattern, top level
    // first, then nested groups. Returns null if there is none.
    function findGroupPath(container, pattern) {
        var i, lyr, sub;
        for (i = 0; i < container.layers.length; i++) {
            lyr = container.layers[i];
            if (lyr.typename === "LayerSet" && pattern.test(lyr.name)) {
                return [i];
            }
        }
        for (i = 0; i < container.layers.length; i++) {
            lyr = container.layers[i];
            if (lyr.typename === "LayerSet") {
                sub = findGroupPath(lyr, pattern);
                if (sub) {
                    return [i].concat(sub);
                }
            }
        }
        return null;
    }

    // Turns off everything except the group at `path` (and the groups that contain it)
    function isolateGroup(container, path, depth) {
        for (var i = 0; i < container.layers.length; i++) {
            var lyr = container.layers[i];
            if (i !== path[depth]) {
                lyr.visible = false;
            } else {
                lyr.visible = true;
                if (depth < path.length - 1) {
                    isolateGroup(lyr, path, depth + 1);
                }
            }
        }
    }

    function trimSide(d, type, top, left, bottom, right) {
        try {
            d.trim(type, top, left, bottom, right);
        } catch (e) {
            // nothing to trim on that side (content touches the edge, or is empty)
        }
    }

    // Trims one side at a time so the size change on each side gives its offset.
    // Returns the content's bounding box in the document's pixels.
    function trimBounds(d, type) {
        var w0 = d.width.as("px");
        var h0 = d.height.as("px");
        trimSide(d, type, true, false, false, false);
        var h1 = d.height.as("px");
        trimSide(d, type, false, false, true, false);
        var h2 = d.height.as("px");
        trimSide(d, type, false, true, false, false);
        var w1 = d.width.as("px");
        trimSide(d, type, false, false, false, true);
        var w2 = d.width.as("px");
        return {
            left: w0 - w1,
            top: h0 - h1,
            right: w0 - (w1 - w2),
            bottom: h0 - (h1 - h2),
            trimmedAnything: (w2 < w0 || h2 < h0)
        };
    }

    // Bounding box of the Main group's visible pixels (masks applied), measured on a
    // copy where everything else is turned off. Returns null if there is no Main group.
    function measureFromMain(doc) {
        var path = findGroupPath(doc, MAIN_GROUP_PATTERN);
        if (!path) {
            return null;
        }
        var probe = doc.duplicate("RH_probe_main");
        try {
            app.activeDocument = probe;
            isolateGroup(probe, path, 0);
            probe.mergeVisibleLayers();
            return trimBounds(probe, TrimType.TRANSPARENT);
        } finally {
            probe.close(SaveOptions.DONOTSAVECHANGES);
            app.activeDocument = doc;
        }
    }

    // Fallback: bounding box of everything that isn't white, on a flattened copy
    function measureFromWhite(doc) {
        var probe = doc.duplicate("RH_probe_white");
        try {
            app.activeDocument = probe;
            probe.flatten();
            if (probe.mode !== DocumentMode.RGB) {
                probe.changeMode(ChangeMode.RGB);
            }
            if (probe.bitsPerChannel !== BitsPerChannelType.EIGHT) {
                probe.bitsPerChannel = BitsPerChannelType.EIGHT;
            }
            // Snap near-white to pure white so Trim ignores faint haze and noise
            probe.activeLayer.adjustLevels(0, WHITE_POINT, 1.0, 0, 255);
            return trimBounds(probe, TrimType.TOPLEFT);
        } finally {
            probe.close(SaveOptions.DONOTSAVECHANGES);
            app.activeDocument = doc;
        }
    }

    // Product bounding box in document pixels, with the shadow already turned off.
    // Prefers the Main group; falls back to the white background and adds a note.
    // The original document is left untouched.
    function measureProduct(doc, notes) {
        var why;
        try {
            var viaMain = measureFromMain(doc);
            if (viaMain === null) {
                why = "no Main group";
            } else if (!viaMain.trimmedAnything) {
                why = "Main group has no empty margin";
            } else {
                viaMain.source = "Main";
                return viaMain;
            }
        } catch (e) {
            why = "Main measure failed: " + e.message;
        }
        notes.push(why + " - used white-trim");
        var viaWhite = measureFromWhite(doc);
        viaWhite.source = "white-trim";
        return viaWhite;
    }

    // 3:2 frame (in source-document pixels, may extend past the canvas) that puts
    // PADDING around the product on every side, centered on the product
    function computeFrame(b) {
        var bw = b.right - b.left;
        var bh = b.bottom - b.top;
        var pad = PADDING * Math.max(bw, bh);
        var w = Math.round(Math.max(bw + 2 * pad, (bh + 2 * pad) * ASPECT));
        var h = Math.round(w / ASPECT);
        return {
            left: Math.round(b.left + bw / 2 - w / 2),
            top: Math.round(b.top + bh / 2 - h / 2),
            w: w,
            h: h
        };
    }

    function px(n) {
        return new UnitValue(n, "px");
    }

    function csvQuote(s) {
        return '"' + String(s).replace(/"/g, '""') + '"';
    }

    function appendLog(logFile, r) {
        var isNew = !logFile.exists;
        logFile.encoding = "UTF-8";
        logFile.open("a");
        if (isNew) {
            logFile.writeln("file,status,srcW,srcH,cropLeft,cropTop,cropW,cropH,outW,outH,hiddenGroups,boundsSource");
        }
        logFile.writeln([
            csvQuote(r.file), csvQuote(r.status), r.srcW, r.srcH,
            r.cropLeft, r.cropTop, r.cropW, r.cropH, r.outW, r.outH,
            csvQuote(r.hidden), csvQuote(r.source)
        ].join(","));
        logFile.close();
    }

    function processFile(file, outFolder) {
        var fileName = decodeURI(file.name);
        var base = fileName.replace(/\.[^\.]+$/, "");
        var r = {
            file: fileName, status: "ok", srcW: "", srcH: "", cropLeft: "", cropTop: "",
            cropW: "", cropH: "", outW: "", outH: "", hidden: "", source: ""
        };
        var notes = [];
        var doc = null;

        try {
            // If the file is already open, work on a copy so the open document is untouched
            var opened = findOpenDoc(file);
            var src = opened ? opened : app.open(file);
            doc = opened ? src.duplicate(base + "_prep") : src;
            app.activeDocument = doc;

            r.srcW = Math.round(doc.width.as("px"));
            r.srcH = Math.round(doc.height.as("px"));

            // 1. Turn off the shadow group(s)
            var hidden = [];
            hideShadowGroups(doc, hidden);
            r.hidden = hidden.join("|");
            if (hidden.length === 0) {
                notes.push("no shadow group found");
            }

            // 2. Find the product and work out the 3:2 padded frame
            var bounds = measureProduct(doc, notes);
            r.source = bounds.source;
            if (!bounds.trimmedAnything) {
                notes.push("no margin found - bounds = full canvas");
            }
            var frame = computeFrame(bounds);
            r.cropLeft = frame.left;
            r.cropTop = frame.top;
            r.cropW = frame.w;
            r.cropH = frame.h;

            // 3. Expand the canvas if the frame extends past it, then crop to the frame
            var cropL = frame.left;
            var cropT = frame.top;
            var growX = Math.max(0, -frame.left, frame.left + frame.w - r.srcW);
            var growY = Math.max(0, -frame.top, frame.top + frame.h - r.srcH);
            if (growX > 0 || growY > 0) {
                doc.resizeCanvas(px(r.srcW + 2 * growX), px(r.srcH + 2 * growY), AnchorPosition.MIDDLECENTER);
                cropL += growX;
                cropT += growY;
            }
            doc.crop([px(cropL), px(cropT), px(cropL + frame.w), px(cropT + frame.h)]);

            // 4. Flatten (discards the hidden shadow group), RGB 8-bit for JPEG
            doc.flatten();
            if (doc.mode !== DocumentMode.RGB) {
                doc.changeMode(ChangeMode.RGB);
            }
            if (doc.bitsPerChannel !== BitsPerChannelType.EIGHT) {
                doc.bitsPerChannel = BitsPerChannelType.EIGHT;
            }

            // 5. Resize so the long side is LONG_EDGE_PX. Output size comes from the aspect
            //    ratio (not the rounded crop), so every file in a batch is exactly the same size.
            if (ASPECT >= 1) {
                r.outW = LONG_EDGE_PX;
                r.outH = Math.round(LONG_EDGE_PX / ASPECT);
            } else {
                r.outH = LONG_EDGE_PX;
                r.outW = Math.round(LONG_EDGE_PX * ASPECT);
            }
            var scale = r.outW / frame.w;
            doc.resizeImage(
                px(r.outW),
                px(r.outH),
                doc.resolution,
                scale < 1 ? ResampleMethod.BICUBICSHARPER : ResampleMethod.BICUBICSMOOTHER
            );

            // 6. Save as JPG and close without saving the PSD
            var outFile = new File(outFolder.fsName + "/" + base + OUTPUT_SUFFIX + ".jpg");
            var jpg = new JPEGSaveOptions();
            jpg.quality = JPEG_QUALITY;
            jpg.embedColorProfile = true;
            jpg.formatOptions = FormatOptions.STANDARDBASELINE;
            doc.saveAs(outFile, jpg, true, Extension.LOWERCASE);

            doc.close(SaveOptions.DONOTSAVECHANGES);
            doc = null;
        } catch (e) {
            r.status = "error: " + e.message + " (line " + e.line + ")";
            try {
                if (doc) {
                    doc.close(SaveOptions.DONOTSAVECHANGES);
                }
            } catch (e2) {
                // already closed
            }
            return r;
        }

        if (notes.length > 0) {
            r.status = "warning: " + notes.join("; ");
        }
        return r;
    }

    // ---------------------------------------------------------------------------

    var files = pickFiles();
    if (!files || files.length === 0) {
        return;
    }

    var outFolder = new Folder(OUTPUT_FOLDER);
    if (!outFolder.exists) {
        outFolder.create();
    }
    var logFile = new File(outFolder.fsName + "/" + LOG_NAME);

    var oldDialogs = app.displayDialogs;
    var oldBG = new SolidColor();
    oldBG.rgb.red = app.backgroundColor.rgb.red;
    oldBG.rgb.green = app.backgroundColor.rgb.green;
    oldBG.rgb.blue = app.backgroundColor.rgb.blue;

    var problems = [];
    var okCount = 0;

    try {
        app.displayDialogs = DialogModes.NO;

        // White canvas extension / flatten fill
        var white = new SolidColor();
        white.rgb.red = 255;
        white.rgb.green = 255;
        white.rgb.blue = 255;
        app.backgroundColor = white;

        for (var i = 0; i < files.length; i++) {
            var res = processFile(files[i], outFolder);
            appendLog(logFile, res);
            if (res.status === "ok") {
                okCount++;
            } else {
                problems.push(res.file + " - " + res.status);
            }
        }
    } finally {
        app.displayDialogs = oldDialogs;
        app.backgroundColor = oldBG;
    }

    var msg = files.length + " file(s) processed, " + okCount + " clean.\nOutput: " + outFolder.fsName;
    if (problems.length > 0) {
        msg += "\n\nCheck these (see " + LOG_NAME + "):\n" + problems.slice(0, 15).join("\n");
        if (problems.length > 15) {
            msg += "\n...and " + (problems.length - 15) + " more";
        }
    }
    alert(msg);
})();
