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

JSON_LAYOUT_FILE = 'layout.json'

class GimpJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        hasattrs = lambda obj,*fields: [f for f in fields if hasattr(obj,f)]
        getattrs = lambda obj,*fields: [(f, getattr(obj,f)) for f in fields]

        item_fields = ['name','width','height']
        extra_fields = ('visible','opacity','mode','offsets','mask','layers')
        
        if hasattrs(obj, *item_fields):
            item_fields.extend(hasattrs(obj, *extra_fields))
            return OrderedDict(getattrs(obj, *item_fields))
            
        return json.JSONEncoder.default(self, obj)

def find_layers(group, name):
    return [l for p,l in getlayers(group) if re.match(name, l.name)]

def find_layer(group, name):
    layers = find_layers(group, name)
    return layers and layers[0] or None

_json_object_hook = lambda d: namedtuple('X', d.keys())(*d.values())
json2obj = lambda data: json.loads(data, object_hook=_json_object_hook)    

def getlayers(group):
    """ Returns a generator of layers and sub-layers
    result is a tuple (group,layer)
    """
    for layer in group.layers:
        yield group, layer
        if hasattr(layer, 'mask'):
                if layer.mask: yield layer,layer.mask
        if hasattr(layer,'layers'):
            for g,l in getlayers(layer):
                yield g,l

#for p,l in getlayers(image): print p, l

def gimp_autocrop_layer(image, layer):
    pdb.gimp_image_set_active_layer(image, layer)
    pdb.plug_in_autocrop_layer(image, layer)

def gimp_export(image, layout, save_path):
    gimp_export_pngs(image, save_path)
    gimp_export_json(image, save_path)

def gimp_export_pngs(image, save_path):
    if not os.path.isdir(save_path):
        os.makedirs(save_path)

    for parent, layer in getlayers(image):
        print 'PNG EXPORT: %s/%s' % (parent.name,layer.name)
        if hasattr(layer, 'layers'):
            #Ignore GroupLayers
            pass
        else:
            # Also export text layers to text files
            if pdb.gimp_item_is_text_layer(layer):
                with open(os.path.join(save_path,layer.name),'w') as f:
                    f.write(pdb.gimp_text_layer_get_text(layer))
            else:
                png_filepath = os.path.join(save_path, layer.name)
                # see pdb.file_png_save & pdb.file_png_save2 for png export options
                pdb.file_png_save_defaults(image, layer, png_filepath, png_filepath)

def gimp_export_json(image, file_path):
    if os.path.isdir(file_path):
        file_path = os.path.join(file_path, JSON_LAYOUT_FILE)
    with open(file_path, 'w') as f:
        f.write(json.dumps(image, cls=GimpJSONEncoder, indent=2))

def gimp_import(file_path):
    if os.path.isdir(file_path):
        file_path = os.path.join(file_path, JSON_LAYOUT_FILE)
    import_path, fname = os.path.split(file_path)
    with open(file_path, 'r') as f:
        source_image = json2obj(f.read())
    image = pdb.gimp_image_new(source_image.width, source_image.height, 0)
    try:
        for source_parent, source_layer in getlayers(source_image):
            print 'PNG IMPORT: %s/%s' % (source_parent.name,source_layer.name)
            parent = find_layer(image, '^%s$' % source_parent.name)
            layer = None
            if hasattr(source_layer,'layers'):
                # Create GroupLayer
                layer = pdb.gimp_layer_group_new(image)
            else:
                # Read file from disk
                image_filepath = os.path.join(import_path,source_layer.name)
                name, ext = os.path.splitext(image_filepath)
                if os.path.isfile(image_filepath):
                    mimetype = mimetypes.guess_type(image_filepath)[0]
                    if mimetype and mimetype.startswith('text'):
                        # Import text Layer
                        with open(image_filepath,'r') as f:
                            text = f.read()
                        layer = pdb.gimp_text_layer_new(image, text, 'Monospace', 24, 0)
                    else:
                        # Import image Layer
                        layer = pdb.gimp_file_load_layer(image, image_filepath)
            if layer:
                # Set layer attributes
                pdb.gimp_item_set_name(layer, source_layer.name)
                pdb.gimp_item_set_visible(layer, source_layer.visible)
                if hasattr(source_layer,'offsets'): pdb.gimp_layer_set_offsets(layer, *source_layer.offsets)
                if hasattr(source_layer,'opacity'): pdb.gimp_layer_set_opacity(layer, source_layer.opacity)
                if hasattr(source_layer,'mode'): pdb.gimp_layer_set_mode(layer, source_layer.mode)
                
                if hasattr(source_parent,'mask') and source_layer == source_parent.mask:
                    # Apply Layer mask
                    pdb.gimp_image_insert_layer(image, layer, None, 0)
                    pdb.gimp_layer_add_alpha(layer)
                    pdb.plug_in_colortoalpha(image, layer, gimpfu.gimpcolor.rgb_names()['black'])
                    pdb.gimp_image_select_item(image,gimpfu.CHANNEL_OP_REPLACE,layer)
                    mask = pdb.gimp_layer_create_mask(parent, gimpfu.ADD_SELECTION_MASK)
                    #import IPython;IPython.embed()
                    pdb.gimp_layer_add_mask(parent, mask)
                    pdb.gimp_selection_none(image)
                    pdb.gimp_image_remove_layer(image,layer)
                    layer = None
                else:
                    # Insert Layer into the Image
                    pdb.gimp_image_insert_layer(image, layer, parent, parent and len(parent.layers) or len(image.layers))

                # Set Text Layer size
                if layer and pdb.gimp_item_is_text_layer(layer): 
                    pdb.gimp_text_layer_resize(layer, source_layer.width, source_layer.height)
    finally:
        # Make sure to display the new  image
        display = pdb.gimp_display_new(image)


#gimp_import_json('/home/nic/workspace/android-emulator-skins/templates/test/' + JSON_LAYOUT_FILE)


class LayerNameError(Exception):
    pass

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

def skin_landscape(image, layer):
    landscape = pdb.gimp_layer_copy(layer, True)
    pdb.gimp_image_insert_layer(image, landscape, None, pdb.gimp_image_get_item_position(image,layer)+1)
    pdb.gimp_item_transform_rotate_simple(landscape, 2, False, image.width/2, image.height/2)
    landscape.name = layer.name.replace('portrait','landscape')

    #Retrieve landscape layer as a LayerGroup
    landscape = find_layer(image,landscape.name)
    for l in landscape.layers:
        l.name = re.sub('(.*)(_port)(\.\w*) ?#?.*', '\\1_land\\3', l.name)

def skin_resize(image, ratio_string='4/3'):
    ratio = map(float, ratio_string.split('/'))
    ratio = ratio[0]/ratio[1]
    background_port = pdb.gimp_image_get_layer_by_name(image, 'background_port.png')
    pdb.gimp_layer_resize(background_port, round(ratio*background_port.height), background_port.height, round(ratio*background_port.height/2) - round(background_port.width/2), 0)
    background_land = pdb.gimp_image_get_layer_by_name(image, 'background_land.png')
    pdb.gimp_layer_resize(background_land, background_port.width, background_port.height, round(background_port.width/2) - round(background_land.width/2), round(background_port.height/2) - round(background_land.height/2))

def skin_update_copy(image_source, ratio_index, scale_index):
    image = pdb.gimp_image_duplicate(image_source)

    for l in image.layers:
        if not l.name in ('hardware.ini','overlay.png', 'portrait'):
            # Hide unrelevant layers
            pdb.gimp_item_set_visible(l, False)

    layer_group_portrait = find_layer(image, 'portrait')
    if scale_index: skin_scale(image, DENSITIES[scale_index][0])
    if not pdb.gimp_image_get_layer_by_name(image, 'landscape'): skin_landscape(image, layer_group_portrait)
    if ratio_index: skin_resize(image, SKIN_RATIOS[ratio_index])
    return image

def extract_layers(image_source, layer, save_path, ratio_index=0, scale_index=0):
    image = skin_update_copy(image_source, ratio_index, scale_index)
    try:
        gimp_export_pngs(image, save_path)
        gimp_export_json(image, save_path)
        skin_export_layout(image, save_path)
    finally:
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
        gimpfu.register("python_fu_layout_export", 
                        "Export Layout", 
                        "Export layers and json", 
                        "Nic", "Nicolas CORNETTE", "2014", 
                        "<Image>/File/Export/Export Layout...", 
                        "*", [
                            (gimpfu.PF_DIRNAME, "load-path", "Path for import", DEFAULT_OUTPUT_DIR),
                              ], 
                        [], 
                        gimp_export) #, menu, domain, on_query, on_run)

        gimpfu.register("python_fu_extract_skin", 
                        "Export Android Skin", 
                        "Export Android Emulator Skin", 
                        "Nic", "Nicolas CORNETTE", "2014", 
                        "<Image>/File/Export/Export Emulator Skin...", 
                        "*", [
                            (gimpfu.PF_DIRNAME, "save-path", "Path for export", DEFAULT_OUTPUT_DIR),
                            (gimpfu.PF_OPTION, "ratio", "Window aspect ratio", 0, SKIN_RATIOS),
                            (gimpfu.PF_OPTION, "scale", "Scale skin", 0, [d[0] for d in DENSITIES]),
                              ], 
                        [], 
                        extract_layers) #, menu, domain, on_query, on_run)

        gimpfu.register("python_fu_layout_import", 
                        "Import Layers", 
                        "Import layers from json and images", 
                        "Nic", "Nicolas CORNETTE", "2014", 
                        "Import Layout...", 
                        "", [
                            (gimpfu.PF_DIRNAME, "import-path", "Path for import", DEFAULT_OUTPUT_DIR),
                              ], 
                        [], 
                        gimp_import, menu='<Image>/File/Export/') #, domain, on_query, on_run)

        gimpfu.main()

