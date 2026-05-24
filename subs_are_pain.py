#! /usr/bin/env python3

import argparse
import cairo
import drawsvg
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

TIMESTAMP_REGEX =  re.compile(r'^([0-9]{2}):([0-9]{2}):([0-9]{2}).([0-9]{3})$')
TIMESTAMP_ZERO = '00:00:00.000'

SRT_TIMESTAMP_REGEX =  re.compile(r'^([0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3}) --> ([0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3})$')

ITEMS_TAG = 'ks'


@dataclass
class SubtitleItem:
    timestamp_from: str
    timestamp_to: str
    timestamp_diff: str
    image_path: Path

    width: int
    height: int

    x: float
    y: float
    w: float
    h: float


def calculate_timestamp_difference(timestamp_from: str, timestamp_to: str):
    msecs_from = timestamp_to_msecs(timestamp_from)
    msecs_to = timestamp_to_msecs(timestamp_to)

    diff = msecs_to - msecs_from
    h = int(diff / 3600000)
    m = int((diff - h * 3600000) / 60000)
    s = int((diff - h * 3600000 - m * 60000) / 1000)
    ms = diff % 1000

    return f'{h:02}:{m:02}:{s:02}.{ms:03}'


def is_valid_timestamp(v: str):
    match = TIMESTAMP_REGEX.match(v)
    if not match:
        return False

    h = int(match.group(1))
    m = int(match.group(2))
    s = int(match.group(3))
    ms = int(match.group(4))

    if h < 0:
        return False
    if not (0 <= m <= 60):
        return False
    if not (0 <= s <= 60):
        return False
    if ms < 0:
        return False

    return True


#
#
# CREATE SUBTITLE IMAGES FROM SRT
#
#

SUB_IMAGES_DIR = 'sub_images'
SVG_FONT_FAMILY = 'DejaVu Sans'
SVG_FONT_SIZE = 32
SVG_LINE_SPACING = '1.25em'
SVG_TEXT_FILL = 'green'
SVG_TEXT_STROKE = 'yellow'
SVG_TEXT_STROKE_WIDTH = 1.1


def horrifying_way_to_measure_text_extent(lines_of_text: List[str]):
    # This uses Cairo to effectively render the text to calculate
    # its size.
    # There does not seem to be anything more straight forward

    max_actual_width = 0
    max_actual_height = 0

    for line in lines_of_text:
        # Use some random very high values for width and height
        surface = cairo.SVGSurface('dummy.svg', 10000, 10000)
        cr = cairo.Context(surface)
        cr.select_font_face(SVG_FONT_FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(SVG_FONT_SIZE)
        _xbearing, _ybearing, _width, height, xadvance, _yadvance = cr.text_extents(line)
        max_actual_width = max(max_actual_width, xadvance)
        max_actual_height = max(max_actual_height, height)

    # We also apply some totally scientifically derived corrections
    # to make sure that the text will *actually* fit into the calculated
    # bouding box
    return (max_actual_width, max_actual_height * len(lines_of_text) * 1.5, max_actual_height / 2)


def create_subtitle_image(lines_of_text: List[str], ident: int, w: int):
    actual_width, actual_height, y_correction = horrifying_way_to_measure_text_extent(lines_of_text)

    dwg = drawsvg.Drawing(actual_width, actual_height)

    text = drawsvg.Text(
        '',
        font_size=SVG_FONT_SIZE,
        font_family=SVG_FONT_FAMILY,
        fill=SVG_TEXT_FILL,
        stroke=SVG_TEXT_STROKE,
        stroke_width=SVG_TEXT_STROKE_WIDTH,
        text_anchor='middle',
        x=actual_width/2, y=-y_correction
    )
    for line in lines_of_text:
        text.append(drawsvg.TSpan(line, x=actual_width/2, dy=SVG_LINE_SPACING))

    dwg.append(text)
    dwg.save_svg(f'{SUB_IMAGES_DIR}/sub_{ident}.svg')

    # To get the PNG of reasonable size
    # we have to scale the SVG up.
    # We use the "width" suppied by the user to calculate the scale factor

    scale_factor = w / actual_width
    png_image_width = w
    png_image_height = actual_height * scale_factor

    dwg_png = drawsvg.Drawing(png_image_width, png_image_height)
    dwg_png.append(drawsvg.Use(text, x=0, y=0, transform=f'scale({scale_factor})'))
    dwg_png.save_png(f'{SUB_IMAGES_DIR}/sub_{ident}.png')


def create_subtitle_images_and_items_from_srt(srt_file_path: Path, left: Optional[float], top: Optional[float], w: float):
    defns = []

    with open(srt_file_path) as fp:
        number = None
        timestamp = None
        lines_of_text = []

        for line in fp.readlines():
            line = line.strip()
            if not line:
                if timestamp and lines_of_text:
                    defns.append((number, timestamp[0], timestamp[1], lines_of_text))
                    number = None
                    timestamp = None
                    lines_of_text = []
                continue

            if not number:
                number = int(line)
            elif not timestamp:
                m = SRT_TIMESTAMP_REGEX.match(line)
                if not m:
                    raise Exception(f'Invalid SRT timestamp {line}')
                timestamp = (m.group(1), m.group(2))
            else:
                lines_of_text.append(line)

    Path(SUB_IMAGES_DIR).mkdir(exist_ok=True)

    sub_items = []
    for number, timestamp_from, timestamp_to, lines_of_text in defns:
        create_subtitle_image(lines_of_text, number, int(w))

        timestamp_from = timestamp_from.replace(',', '.')
        timestamp_to = timestamp_to.replace(',', '.')

        if not is_valid_timestamp(timestamp_from):
            raise Exception(f'Timestamp {timestamp_from} is invalid')
        if not is_valid_timestamp(timestamp_to):
            raise Exception(f'Timestamp {timestamp_to} is invalid')

        timestamp_diff = calculate_timestamp_difference(timestamp_from, timestamp_to)

        image_path = Path(f'{SUB_IMAGES_DIR}/sub_{number}.png').absolute()
        image = Image.open(image_path)
        width, height = image.size

        item = SubtitleItem(
            timestamp_from,
            timestamp_to,
            timestamp_diff,
            image_path,
            width,
            height,
            left if left else 0,
            top if top else 0,
            width,
            height
        )
        sub_items.append(item)

    return sub_items


#
#
# MAKE SUBTITLE TIMELINE FROM SRT
#
#

def create_subtitle_items_from_srt(srt_file_path: Path, left: Optional[float], top: Optional[float], w: Optional[float], h: Optional[float]):
    defns = []

    with open(srt_file_path) as fp:
        number = None
        timestamp = None
        image_path = ''

        for line in fp.readlines():
            line = line.strip()
            if not line:
                if timestamp and image_path:
                    defns.append((number, timestamp[0], timestamp[1], image_path))
                    number = None
                    timestamp = None
                    image_path = ''
                continue

            if not number:
                number = int(line)
            elif not timestamp:
                m = SRT_TIMESTAMP_REGEX.match(line)
                if not m:
                    raise Exception(f'Invalid SRT timestamp {line}')
                timestamp = (m.group(1), m.group(2))
            elif not image_path:
                image_path = line
            # This purposefully ignores any extra lines of text
            # because we cannot really do anything with them anyway

    sub_items = []
    for number, timestamp_from, timestamp_to, image_path in defns:
        timestamp_from = timestamp_from.replace(',', '.')
        timestamp_to = timestamp_to.replace(',', '.')

        if not is_valid_timestamp(timestamp_from):
            raise Exception(f'Timestamp {timestamp_from} is invalid')
        if not is_valid_timestamp(timestamp_to):
            raise Exception(f'Timestamp {timestamp_to} is invalid')

        timestamp_diff = calculate_timestamp_difference(timestamp_from, timestamp_to)

        image_path = Path(image_path).absolute()
        image = Image.open(image_path)
        # This is the real size of the image. That can be different
        # from the size we will scale the image to for rendering
        width, height = image.size

        item = SubtitleItem(
            timestamp_from,
            timestamp_to,
            timestamp_diff,
            image_path,
            width,
            height,
            left if left else 0,
            top if top else 0,
            w if w else width,
            h if h else height
        )
        sub_items.append(item)

    return sub_items


#
# UTILITY FUNCTIONS FOR MLT MANIPULATION
#

def add_boilerplate(xml_elem, boilerplate: List[Tuple[str, str]]):
    for name, value in boilerplate:
        ET.SubElement(xml_elem, 'property', name=name).text = value


def timestamp_to_msecs(timestamp: str):
    match = TIMESTAMP_REGEX.match(timestamp)
    assert match != None

    h = int(match.group(1))
    m = int(match.group(2))
    s = int(match.group(3))
    ms = int(match.group(4))

    return h * 3600000 + m * 60000 + s * 1000 + ms


def make_subtitle_producer_id(idx):
    return f'producer_{ITEMS_TAG}_{idx}'


def add_images_to_main_bin(mlt_root, sub_items):
    for child in mlt_root:
        if child.tag == 'playlist' and child.attrib['id'] == 'main_bin':
            for (idx, sub_item) in enumerate(sub_items):
                xml_elem = ET.SubElement(child, 'entry', producer=make_subtitle_producer_id(idx))
                xml_elem.attrib['in'] = sub_item.timestamp_from
                xml_elem.attrib['out'] = sub_item.timestamp_to

            return

    raise Exception('"main_bin" not found in the MLT file')


def playlist_create_element(sub_items: List[SubtitleItem]):
    xml_elem = ET.Element('playlist', id=f'playlist_{ITEMS_TAG}')
    ET.SubElement(xml_elem, 'property', name='shotcut:video').text = '1'
    ET.SubElement(xml_elem, 'property', name='shotcut:name').text = 'K Subtitles'

    for (idx, sub_item) in enumerate(sub_items):
        if idx > 0:
            prev_sub_item = sub_items[idx - 1]
            timestamp_diff = calculate_timestamp_difference(prev_sub_item.timestamp_to, sub_item.timestamp_from)
            if timestamp_diff != TIMESTAMP_ZERO:
                xml_blank = ET.SubElement(xml_elem, 'blank', length = timestamp_diff)

        e = ET.SubElement(xml_elem, 'entry', producer=make_subtitle_producer_id(idx))
        e.attrib['in'] = TIMESTAMP_ZERO
        e.attrib['out'] = sub_item.timestamp_diff

    #
    # If the first subtitle item does not appear right at the start of the video
    # we need to pad the playlist out with a "blank" element
    #
    if sub_items[0].timestamp_from != TIMESTAMP_ZERO:
        xml_blank = ET.Element('blank', length = sub_items[0].timestamp_from)
        xml_elem.insert(0, xml_blank)

    return xml_elem


def playlist_add_to_tractor(mlt_root, xml_playlist_elem):

    for (idx, child) in enumerate(mlt_root):
        if child.tag == 'tractor' and child.attrib['id'] == 'tractor0':
            mlt_root.insert(idx - 1, xml_playlist_elem)

            ET.SubElement(child, 'track', producer=f'playlist_{ITEMS_TAG}')

            #
            # Add transitions too, otherwise the track will cover up
            # all tracks below it
            #
            num_tracks = 0
            for tractor_child in child:
                if tractor_child.tag == 'track':
                    num_tracks += 1

            xml_transition = ET.SubElement(child, 'transition', id=f'transition_{ITEMS_TAG}_0')
            BOILERPLATE_A = [
                ('a_track', '0'),
                ('b_track', str(num_tracks - 1)),
                ('mlt_service', 'mix'),
                ('always_active', '1'),
                ('sum', '1')
            ]
            add_boilerplate(xml_transition, BOILERPLATE_A)

            xml_transition = ET.SubElement(child, 'transition', id=f'transition_{ITEMS_TAG}_1')
            BOILERPLATE_B = [
                ('a_track', '1'),
                ('b_track', str(num_tracks - 1)),
                ('compositing', '0'),
                ('distort', '0'),
                ('rotate_center', '0'),
                ('mlt_service', 'qtblend'),
                ('threads', '0'),
                ('disable', '0')
            ]
            add_boilerplate(xml_transition, BOILERPLATE_B)

            return

    raise Exception('tractor0 not found in the MLT file')


def subtitle_add_boilerplate(xml_elem, sub_item: SubtitleItem):
    BOILERPLATE = [
        ('eof', 'pause'),
        ('ttl', '1'),
        ('aspect_ratio', '1'),
        ('meta.media.progressive', '1'),
        ('seekable', '1'),
        ('format', '1'),
        ('mlt_service', 'qimage'),
        ('xml', 'was_here'),
        ('meta.shortcut.vui', '1')
    ]

    ET.SubElement(xml_elem, 'property', name='length').text = sub_item.timestamp_diff
    add_boilerplate(xml_elem, BOILERPLATE)


def subtitle_add_image_subelements(xml_elem, sub_item: SubtitleItem):
    caption = sub_item.image_path.name

    ET.SubElement(xml_elem, 'property', name='meta.media.width').text = str(sub_item.width)
    ET.SubElement(xml_elem, 'property', name='meta.media.height').text = str(sub_item.height)
    ET.SubElement(xml_elem, 'property', name='shotcut:caption').text = str(caption)
    ET.SubElement(xml_elem, 'property', name='resource').text = str(sub_item.image_path.absolute())


def subtitle_add_positioning_and_scaling_subelements(xml_elem, sub_item: SubtitleItem, idx: int):
    BOILERPLATE = [
        ('background', 'color:#00000000'),
        ('mlt_service', 'affine'),
        ('shotcut:filter', 'affineSizePosition'),
        ('transition.fix_rotate_x', '0'),
        ('transition.fill', '1'),
        ('transition.distort', '1'),
        ('transition.valign', 'center'),
        ('transition.halign', 'middle'),
        ('transition.threads', '0'),
        ('shotcut:animIn', TIMESTAMP_ZERO),
        ('shotcut:animOut', TIMESTAMP_ZERO)
    ]

    xml_filter = ET.SubElement(xml_elem, 'filter', id=f'filter_{ITEMS_TAG}_{idx}')
    xml_filter.attrib['in'] = TIMESTAMP_ZERO
    xml_filter.attrib['out'] = sub_item.timestamp_diff

    add_boilerplate(xml_filter, BOILERPLATE)

    ET.SubElement(xml_filter, 'property', name='transition.rect').text = f'{sub_item.x} {sub_item.y} {sub_item.w} {sub_item.h} 1'


def subtitle_make_element(idx: int, sub_item: SubtitleItem):
    xml_elem = ET.Element('producer', id=f'producer_{ITEMS_TAG}_{idx}')
    xml_elem.attrib['in'] = TIMESTAMP_ZERO
    xml_elem.attrib['out'] = sub_item.timestamp_diff

    subtitle_add_boilerplate(xml_elem, sub_item)
    subtitle_add_image_subelements(xml_elem, sub_item)
    subtitle_add_positioning_and_scaling_subelements(xml_elem, sub_item, idx)

    return xml_elem


def make_argparse():
    ap = argparse.ArgumentParser(conflict_handler='resolve')
    ap.add_argument('-i', '--mlt-in', type=Path, help='Path to input MLT file')
    ap.add_argument('-o', '--mlt-out', type=Path, help='Path to output MLT file')
    ap.add_argument('-s', '--srt', type=Path, help='Path to SRT file with information how to make and add subtitles')
    ap.add_argument(
        '-m',
        '--srt-mode',
        choices=['create', 'use'],
        help="""How to use the content of the SRT file."""
             """ "create" reads the SRT as if it contained real subtitles, makes SVG and PNG images for each subtitle item and creates the playlist in the MLT file. Editing the SVG files and exporting them to PNG will update the subtitles in the video. "use" assumes that each subtitle item contains *a path to the image that is to be used as the subtitles*. The image must be in a format that Shotcut can work with."""
    )
    ap.add_argument('-t', '--top', type=float, help='Position of the center subtitle text from the top')
    ap.add_argument('-l', '--left', type=float, help='Position of the center subtitle text from the left')
    ap.add_argument('-w', '--width', type=int, nargs='?', help='Width of the subtitle text. Supplying the width is mandatory when the script is run in "create" mode')
    ap.add_argument('-h', '--height', type=int, nargs='?', help='Height of the subtitle text')

    return ap


def create_subtitle_items(mode: str, srt: Path, left: float, top: float, w: Optional[float], h: Optional[float]):
    if mode == 'create':
        if not w:
            raise Exception('Subtitle text width and height must be set in "create" mode')
        return create_subtitle_images_and_items_from_srt(srt, left, top, w)
    elif mode == 'use':
        return create_subtitle_items_from_srt(srt, left, top, w, h)

    assert False, 'Bad mode'


def main():
    ap = make_argparse()
    parsed = ap.parse_args()

    mlt_tree = ET.parse(parsed.mlt_in)
    sub_items = create_subtitle_items(
        parsed.srt_mode,
        parsed.srt,
        parsed.left,
        parsed.top,
        parsed.width,
        parsed.height
    )

    if not sub_items:
        raise Exception('No subtitle items')

    mlt_root = mlt_tree.getroot()
    for idx, sub_item in enumerate(sub_items):
        xml_elem = subtitle_make_element(idx, sub_item)
        mlt_root.insert(1, xml_elem)

    add_images_to_main_bin(mlt_root, sub_items)

    xml_playlist_elem = playlist_create_element(sub_items)
    playlist_add_to_tractor(mlt_root, xml_playlist_elem)

    mlt_tree.write(parsed.mlt_out)


if __name__ == '__main__':
    main()
