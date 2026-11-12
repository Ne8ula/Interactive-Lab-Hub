# Classifier models

[Pi shelf-camera model 2](a4-pi-v2/README.md) is the current A4 model. It was
trained and exported on 2026-11-10 using 184 WORK, 163 VIDEO, and 200 NEUTRAL
images from the Pi camera. The [Kiyo baseline](a4-kiyo-v1/README.md) is retained
for comparison; the course stock model remains separate on the Pi.

The [manual switching test](../README.md#a4-teachable-machine)
records 94.7% correct on 872 labeled frames in one short recording. Bright
fullscreen video and a different neutral wallpaper caused errors. This model
was used in the [Part B experiments](../README.md#part-b-shelf-watcher-interaction) and
[finished companion](../README.md#part-2--finished-system-in-use). Split-screen layouts and
lighting changes remain known limitations.

See the model-specific README for preprocessing, class order, hashes, and Pi
launch instructions. Raw optical captures and editable training project backups
stay in ignored data folders. [All A4 evidence](../README.md#a4-teachable-machine).
