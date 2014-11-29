#! /usr/bin/env python

import re
import sys
import os
import json
from pipes import quote
from string import Template
from collections import namedtuple
from collections import OrderedDict
import mimetypes
mimetypes.add_type('text/plain','.ini')

DENSITIES = (
    # name, (density, min, max)
    ('DEFAULT',(0,0,0)),
    ('ldpi',(120,120,139)),
    ('mdpi',(160,140,199)),
    ('hdpi',(240,200,279)),
    ('xhdpi',(320,280,399)),
    ('xxhdpi',(480,400,559)),
    ('xxxhdpi',(640,560,719))
    )
DENSITIES_MAP = dict(DENSITIES)
SKIN_RATIOS = ('DEFAULT', '4/3', '16/9')

LAYOUT = Template("""
parts {
   device {
        display {
            width   ${screen_port_width}
            height  ${screen_port_height}
            x       0
            y       0
        }
    }
    
    portrait {
        background {
            image   background_port.png
        }

        buttons {
            ${buttons_port}
        }
    }
    
    landscape {
        background {
            image   background_land.png
        }

        buttons {
            ${buttons_land}
        }
    }
}

layouts {
    portrait {
        width     ${background_port_width}
        height    ${background_port_height} 
        color     0x555555
        
        part1 {
            name    portrait
            x       0
            y       0
        }

        part2 {
            name    device
            x       $screen_port_x
            y       $screen_port_y
        }
    }
    
    landscape {
        width     ${background_land_width}
        height    ${background_land_height}
        color     0x555555
        
        part1 {
            name    landscape
            x       0
            y       0
        }

        part2 {
            name   device
            x      $screen_land_x
            y      $screen_land_y
            rotation 3
        }
    }
}

""")

BUTTON = Template("""
            ${button_name} {
                image   ${button_name}_${orientation}.png
                x       ${button_x}
                y       ${button_y}
            }""")

class LayerNameError(Exception):
    pass

def getlayers(group):
    """ Returns a generator of layers and sub-layers
    result is a tuple (parent,layer)
    """
    for layer in group.layers:
        yield group, layer
        if hasattr(layer, 'mask'):
                if layer.mask: yield layer,layer.mask
        if hasattr(layer,'layers'):
            for g,l in getlayers(layer):
                yield g,l

def find_layers(group, name):
    return [l for p,l in getlayers(group) if re.match(name, l.name)]

def find_layer(group, name):
    layers = find_layers(group, name)
    return layers and layers[0] or None

def skin_export_layout(image, save_path):

    port_layers = find_layer(image, 'portrait')
    land_layers = find_layer(image, 'landscape')
    screen_port = find_layer(port_layers, 'screen_port.png')
    screen_land = find_layer(land_layers, 'screen_land.png')
    background_port = find_layer(port_layers, 'background_port.png')
    background_land = find_layer(land_layers, 'background_land.png')

    skin_layout = {}
    skin_layout['screen_port_width']=screen_port.width
    skin_layout['screen_port_height']=screen_port.height

    skin_layout['background_port_width']  = background_port.width
    skin_layout['background_port_height'] = background_port.height
    skin_layout['background_land_width']  = background_land.width
    skin_layout['background_land_height'] = background_land.height
    
    skin_layout['screen_port_x'] = screen_port.offsets[0] - background_port.offsets[0]
    skin_layout['screen_port_y'] = screen_port.offsets[1] - background_port.offsets[1]
    skin_layout['screen_land_x'] = screen_land.offsets[0] - background_land.offsets[0]
    skin_layout['screen_land_y'] = screen_land.offsets[1] - background_land.offsets[1] + screen_land.height

    fullname_parser = re.compile('^(.*)_(\w*)\.?.*$')
    
    button_layers = find_layers(port_layers, '[^(background|screen)]') + find_layers(land_layers, '[^(background|screen)]')

    buttons = dict(land = [],port = [])

    for layer in button_layers:
        try:
            button_name, orientation = fullname_parser.findall(layer.name)[0]
            orientation = orientation[:4].lower()
            background_layer = orientation == 'port' and background_port or background_land
            buttons[orientation].append(BUTTON.substitute({
                'button_name':button_name,
                'orientation':orientation,
                'button_x': layer.offsets[0] - background_layer.offsets[0],
                'button_y': layer.offsets[1] - background_layer.offsets[1]}))
        except e:
            raise LayerNameError(e, """Cannot identify button layer with name: \n"%s"\n\nName must be like: "<button_key>_port.png" or "<button_key>_land.png".\n\n""" % layer.name)
    
    skin_layout['buttons_port'] = ''.join(buttons['port'])
    skin_layout['buttons_land'] = ''.join(buttons['land'])
    
    layout_filepath = os.path.join(save_path, 'layout')
    with open(layout_filepath, 'w') as f:
        f.write(LAYOUT.substitute(skin_layout))

def skin_scale(image, target_density):
    hardware_layer = find_layer(image,'hardware.ini')
    hardware_config = pdb.gimp_text_layer_get_text(hardware_layer)
    hardware_layer.name = 'old_hardware.ini'
    skin_density = int(re.findall('hw.lcd.density\W*=\W*(\d*).*', hardware_config)[0])
    ref_skin_density = [d[1][0] for d in DENSITIES_MAP.iteritems() if skin_density in range(d[1][1],d[1][2])][0]
    target_density_value = DENSITIES_MAP.get(target_density)[0]
    scale = float(target_density_value) / ref_skin_density
    pdb.gimp_image_scale(image, round(scale*image.width), round(scale*image.height))
    hardware_config_scaled = re.sub('(.*hw.lcd.density\W*=\W*)(\d*)(.*)', '\\g<1>%d\\g<3>' % int(scale * skin_density), hardware_config)
    hardware_layer_copy = pdb.gimp_text_layer_new(image, hardware_config, 'Monospace', 24, 0)
    pdb.gimp_image_insert_layer(image, hardware_layer_copy, None, pdb.gimp_image_get_item_position(image,hardware_layer))
    pdb.gimp_item_set_name(hardware_layer_copy, 'hardware.ini')
    pdb.gimp_layer_set_offsets(hardware_layer_copy, *hardware_layer.offsets)
    pdb.gimp_text_layer_resize(hardware_layer_copy, hardware_layer.width, hardware_layer.height)
    pdb.gimp_text_layer_set_text(hardware_layer_copy, hardware_config_scaled)
    pdb.gimp_image_remove_layer(image,hardware_layer)

def skin_rotate_group(image, layer, direction):
    rotation = {'portrait':gimpfu.ROTATE_270,'landscape':gimpfu.ROTATE_90}
    angle = rotation[direction[0]]
    
    old_layer = pdb.gimp_image_get_layer_by_name(image, direction[1])
    pdb.gimp_image_remove_layer(image,old_layer) if old_layer else None

    new_layer = pdb.gimp_layer_copy(layer, True)
    pdb.gimp_item_set_visible(new_layer, False)
    pdb.gimp_image_insert_layer(image, new_layer, None, pdb.gimp_image_get_item_position(image,layer)+1)
    pdb.gimp_item_transform_rotate_simple(new_layer, angle, False, image.width/2, image.height/2)
    new_layer.name = layer.name.replace(*direction)

    #Retrieve new_layer as a LayerGroup
    new_layer = find_layer(image,new_layer.name)
    for l in new_layer.layers:
        l.name = re.sub('(.*)(_%s)(\.\w*) ?#?.*' % direction[0][:4], '\\1_%s\\3' % direction[1][:4], l.name)

def skin_resize(image, ratio_string='4/3'):
    ratio = map(float, ratio_string.split('/'))
    ratio = ratio[0]/ratio[1]
    background_port = pdb.gimp_image_get_layer_by_name(image, 'background_port.png')
    pdb.gimp_layer_resize(background_port, round(ratio*background_port.height), background_port.height, round(ratio*background_port.height/2) - round(background_port.width/2), 0)
    background_land = pdb.gimp_image_get_layer_by_name(image, 'background_land.png')
    pdb.gimp_layer_resize(background_land, background_port.width, background_port.height, round(background_port.width/2) - round(background_land.width/2), round(background_port.height/2) - round(background_land.height/2))

def skin_update_copy(image_source, ratio_index, scale_index):
    image = pdb.gimp_image_duplicate(image_source)
    pdb.gimp_image_undo_disable(image)
    direction = ['portrait','landscape']
    layer_orientation = [layer.name for layer in image.layers if layer.name in direction][0]
    direction.insert(0, direction.pop()) if layer_orientation == direction[1] else None

    layer_group = find_layer(image, direction[0])
    if scale_index: skin_scale(image, DENSITIES[scale_index][0])
    target_group = pdb.gimp_image_get_layer_by_name(image, direction[1])
    if not target_group or not target_group.visible: skin_rotate_group(image, layer_group, direction)
    if ratio_index: skin_resize(image, SKIN_RATIOS[ratio_index])
    pdb.gimp_image_undo_enable(image)
    return image

def skin_export(image_source, layer, save_path, ratio_index=0, scale_index=0):
    image = skin_update_copy(image_source, ratio_index, scale_index)
    try:
        pdb.python_fu_layout_export(image, None, save_path, False, False, True)
        skin_export_layout(image, save_path)
    finally:
        #display = pdb.gimp_display_new(image)
        pdb.gimp_image_delete(image)

if __name__=='__main__':

    try:
        pdb
        interactive = False
    except NameError, e:
        interactive = True
    
    if not interactive:
        xcf_path = os.environ.get('XCF_FILE')
        if xcf_path:
            png_path = os.path.splitext(xcf_path)[0]
            image = pdb.gimp_xcf_load(0, xcf_path, xcf_path)
            extract_layers(image, None, png_path)

    else:
        import gimpfu
        pdb = gimpfu.pdb
        DEFAULT_OUTPUT_DIR = os.getcwd()
        gimpfu.register("python_fu_extract_skin", 
                        "Export Android Skin", 
                        "Export Android Emulator Skin", 
                        "Nic", "Nicolas CORNETTE", "2014", 
                        "<Image>/File/Export/Export Emulator Skin...", 
                        "*", [
                            (gimpfu.PF_DIRNAME, "save-path", "Export Path", DEFAULT_OUTPUT_DIR),
                            (gimpfu.PF_OPTION, "ratio", "Window aspect ratio", 0, SKIN_RATIOS),
                            (gimpfu.PF_OPTION, "scale", "Scale skin", 0, [d[0] for d in DENSITIES]),
                              ], 
                        [], 
                        skin_export) #, menu, domain, on_query, on_run)

        gimpfu.main()

