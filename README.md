# A somewhat automated generator of fancy-ish subtitles for the Shotcut video editor

## Requirements
The script requires `pycairo`, `drawsvg` and `pillow` packages to run.

## How does it work?
I find the Shotcut builtin text editing tools a bit too simple to create nicely
looking text captions. One possible solution is to create all the text in
a more sophisticated graphics editor and place it in the video timeline. That
provides the ultimate flexibility but is quite tedious. This script can automate
some parts of this.

This script can operate in two modes, _use_ and _create_. Details are discussed below.
Both modes rely on SRT file to get the timing information.


## The "use" mode
The *use* mode assumes that all images with the text to put into the video are
already drawn. What needs to be done is to put them into the video. To do that,
we need a SRT file to match up the images with timestamps.

The suggested workflow is:
- Create images with the text
- Create a SRT file to match up times in a video to the images. The "text" in
  the SRT file should be a path to the image.
  You can use either relative or absolute paths to the images.
- Run the script like this

```
./subs_are_pain.py --mlt-in video.mlt --mlt-out video_with_subs.mlt --srt cue.srt  --srt-mode use --top 1200 --left 20
```

An example SRT file can look like this:
```
1
00:00:00,324 --> 00:00:00,457
assets/subs_1.png

2
00:00:00,457 --> 00:00:00,666
assets/subs_2.png

3
00:00:00,666 --> 00:00:00,930
assets/subs_3.png

4
00:00:00,930 --> 00:00:01,930
assets/subs_4.png

5
00:00:02,334 --> 00:00:02,689
assets/subs_5.png
```

## The "create" mode
The *create* mode creates all images that will be displayed as subtitles in the
video. Images are created in both SVG and PNG so that the image can be easily
edited. After creating the images the script also places them in the video
timeline.

The suggested workflow is:
- Create a SRT file with the intended subtitles
- Run the script like this

```
./subs_are_pain.py --mlt-in video.mlt --mlt-out video_with_subs.mlt --srt subs.srt  --srt-mode create --top 1200 --left 20 --width 1000
```

An example SRT file can look like this:
```
1
00:00:00,324 --> 00:00:01,426
Have a
nice day!

2
00:00:02,334 --> 00:00:02,689
😈
```

- Adjust the generated files as needed and regenerate the PNG files. Reloading
  the project in Shotcut should update the subtitles. In is not necessary to
  run the script again
