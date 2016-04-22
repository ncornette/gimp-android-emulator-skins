#! /usr/bin/env python

import re
import os
import functools
import json as _json

from collections import namedtuple
from collections import OrderedDict
import mimetypes
mimetypes.add_type('text/plain', '.ini')

gimp_required_fields = ('name', 'width', 'height')
gimp_extra_fields = ('visible', 'linked', 'opacity', 'mode', 'offsets', 'mask', 'layers')

JSON_LAYOUT_FILE = 'layout.json'


def owned_attrs(o, *fields):
    return [f for f in fields if hasattr(o, f)]


def hasattrs(o, *fields):
    return len(owned_attrs(o, *fields)) == len(fields)


def getattrs(o, *fields):
    return [(f, getattr(o, f)) for f in fields]


def as_ordered_dict(obj, required_attrs, extra_attrs):
    object_attrs = list(required_attrs)

    if hasattrs(obj, *required_attrs):
        object_attrs.extend(owned_attrs(obj, *extra_attrs))
        return OrderedDict(getattrs(obj, *object_attrs))


def _json_object_hook(d):
    return namedtuple('GimpObject', d.keys())(*d.values())


class GimpJSONEncoder(_json.JSONEncoder):
    def default(self, obj):
        return as_ordered_dict(obj, gimp_required_fields, gimp_extra_fields) or \
            _json.JSONEncoder.default(self, obj)


# Customize my json
json = namedtuple('GimpJson', 'load loads dump dumps')(
        load=functools.partial(_json.load, object_hook=_json_object_hook),
        loads=functools.partial(_json.loads, object_hook=_json_object_hook),
        dump=functools.partial(_json.dump, cls=GimpJSONEncoder, indent=2),
        dumps=functools.partial(_json.dumps, cls=GimpJSONEncoder, indent=2),
)


def getlayers(group):
    """ Returns a generator of layers and sub-layers
    result is a tuple (parent,layer)
    """
    for layer in group.layers:
        yield group, layer
        if hasattr(layer, 'mask'):
            if layer.mask:
                yield layer, layer.mask
        if hasattr(layer, 'layers'):
            for g, l in getlayers(layer):
                yield g, l


def find_layers(group, name):
    return [l for p, l in getlayers(group) if re.match(name, l.name)]


def find_layer(group, name):
    layers = find_layers(group, name)
    return layers and layers[0] or None


def gimp_autocrop_layer(image, layer):
    pdb.gimp_image_set_active_layer(image, layer)
    pdb.plug_in_autocrop_layer(image, layer)


def gimp_export_pngs(image, save_path):
    if not os.path.isdir(save_path):
        os.makedirs(save_path)

    for parent, layer in getlayers(image):
        print 'PNG EXPORT: %s/%s' % (parent.name, layer.name)
        if hasattr(layer, 'layers'):
            # Ignore GroupLayers
            pass
        else:
            # Also export text layers to text files
            if pdb.gimp_item_is_text_layer(layer):
                with open(os.path.join(save_path, layer.name), 'w') as f:
                    f.write(pdb.gimp_text_layer_get_text(layer))
            else:
                png_filepath = os.path.join(save_path, layer.name)
                # see pdb.file_png_save & pdb.file_png_save2 for png export options
                pdb.file_png_save2(image, layer, png_filepath, png_filepath,
                                   0,  # 0 'interlace PDB_INT32: Use Adam7 interlacing?'
                                   9,
                                   # 9 'compression PDB_INT32: Deflate Compression factor (0--9)'
                                   1,  # 1 'bkgd PDB_INT32: Write bKGD chunk?' Save background color
                                   0,  # 0 'gama PDB_INT32: Write gAMA chunk?' Save Gamma
                                   0,  # 0 'offs PDB_INT32: Write oFFs chunk?' Sale layer offset
                                   1,  # 1 'phys PDB_INT32: Write pHYs chunk?' Save resolution

                                   # 0 to not alter png file content
                                   0,  # 1 'time PDB_INT32: Write tIME chunk?' Save creation time

                                   1,  # 1 'comment PDB_INT32: Write comment?' Save comment
                                   1,
                                   # 1 'svtrans PDB_INT32: Preserve color of transparent pixels?'
                                   )


def gimp_export_json(image, file_path):
    if not os.path.isdir(file_path):
        os.makedirs(file_path)
    file_path = os.path.join(file_path, JSON_LAYOUT_FILE)
    with open(file_path, 'w') as f:
        json.dump(image, f)


def gimp_import_json(file_path):
    file_path = os.path.join(file_path, JSON_LAYOUT_FILE)
    with open(file_path, 'r') as f:
        return json.load(f)


def gimp_import_pngs(image_obj, import_path):
    """Import image object into new Gimp image, reading pictures from import_path
    :param image_obj:
    :param import_path:
    """
    gimp_image = pdb.gimp_image_new(image_obj.width, image_obj.height, 0)
    pdb.gimp_image_undo_disable(gimp_image)
    pdb.gimp_image_set_filename(gimp_image, image_obj.name)
    try:
        _gimp_file_import_layers(getlayers(image_obj), gimp_image, import_path)
    finally:
        # Make sure to display the new  image
        pdb.gimp_image_undo_enable(gimp_image)
        display = pdb.gimp_display_new(gimp_image)


def _gimp_file_import_layers(layers, image, import_path):
    """Import layers into the image, reading pictures from import_path+"/"+layer.name
    """
    for source_parent, source_layer in layers:
        print 'PNG IMPORT: %s/%s' % (source_parent.name, source_layer.name)
        parent = find_layer(image, '^%s$' % source_parent.name)
        if hasattr(source_layer, 'layers'):
            # Create GroupLayer
            layer = pdb.gimp_layer_group_new(image)
        else:
            # Read file from disk & create new Layer
            image_filepath = os.path.join(import_path, source_layer.name)
            name, ext = os.path.splitext(image_filepath)
            if os.path.isfile(image_filepath):
                mimetype = mimetypes.guess_type(image_filepath)[0]
                if mimetype and mimetype.startswith('text'):
                    # Import text Layer
                    with open(image_filepath, 'r') as f:
                        text = f.read()
                    layer = pdb.gimp_text_layer_new(image, text, 'Monospace', 24, 0)
                else:
                    # Import image Layer
                    layer = pdb.gimp_file_load_layer(image, image_filepath)
            else:
                layer = None

        if layer:
            # Set layer attributes
            pdb.gimp_item_set_name(layer, source_layer.name)
            pdb.gimp_item_set_visible(layer, source_layer.visible)
            hasattr(source_layer, 'linked') and pdb.gimp_item_set_linked(layer, source_layer.linked)
            hasattr(source_layer, 'offsets') and pdb.gimp_layer_set_offsets(layer,
                                                                            *source_layer.offsets)
            hasattr(source_layer, 'opacity') and pdb.gimp_layer_set_opacity(layer,
                                                                            source_layer.opacity)
            hasattr(source_layer, 'mode') and pdb.gimp_layer_set_mode(layer, source_layer.mode)
            if hasattr(source_parent, 'mask') and source_layer == source_parent.mask:
                # Insert Layer into the Image
                pdb.gimp_image_insert_layer(image, layer, None, 0)
                # Apply Layer mask
                pdb.gimp_layer_add_alpha(layer)
                pdb.plug_in_colortoalpha(image, layer, gimpfu.gimpcolor.rgb_names()['black'])
                pdb.gimp_image_select_item(image, gimpfu.CHANNEL_OP_REPLACE, layer)
                mask = pdb.gimp_layer_create_mask(parent, gimpfu.ADD_SELECTION_MASK)
                pdb.gimp_layer_add_mask(parent, mask)
                pdb.gimp_selection_none(image)
                pdb.gimp_image_remove_layer(image, layer)
                # layer has been used to create layer mask, can be removed
                layer = None
            else:
                # Insert Layer into the Image
                pdb.gimp_image_insert_layer(image, layer, parent,
                                            parent and len(parent.layers) or len(image.layers))

            # Set Text Layer size
            if layer and pdb.gimp_item_is_text_layer(layer):
                pdb.gimp_text_layer_resize(layer, source_layer.width, source_layer.height)


def create_copy(image, only_visible=False, crop_visible=False, crop_linked=False):
    delete_layers = []
    image_copy = pdb.gimp_image_duplicate(image)
    pdb.gimp_image_undo_disable(image_copy)
    pdb.gimp_image_set_filename(image_copy, image.name)
    for parent, layer in getlayers(image_copy):
        if only_visible and not layer.visible:
            delete_layers.append(layer)
            continue
        if crop_visible and layer.visible:
            gimp_autocrop_layer(image_copy, layer)
        elif crop_linked and layer.linked:
            gimp_autocrop_layer(image_copy, layer)

    for l in delete_layers:
        pdb.gimp_image_remove_layer(image_copy, l)

    return image_copy


def gimp_export(image, layout, save_path, only_visible=False, crop_visible=False,
                crop_linked=False):
    img = create_copy(image, only_visible, crop_visible, crop_linked)
    try:
        gimp_export_json(img, save_path)
        gimp_export_pngs(img, save_path)
    finally:
        pdb.gimp_image_delete(img)


def gimp_import(load_path):
    img = gimp_import_json(load_path)
    gimp_import_pngs(img, load_path)


try:
    import gimpfu
    from gimpfu import pdb

    DEFAULT_OUTPUT_DIR = os.getcwd()

    gimpfu.register("python_fu_layout_export",
                    "Export Layout",
                    "Export layers and json",
                    "Nic", "Nicolas CORNETTE", "2014",
                    "<Image>/File/Export/Export Layout...",
                    "*", [
                        (gimpfu.PF_DIRNAME, "export-path", "Export Path", DEFAULT_OUTPUT_DIR),
                        (gimpfu.PF_BOOL, "only_visible", "  Export Visible Only", False),
                        (gimpfu.PF_BOOL, "crop_visible", "  Auto Crop Visible", False),
                        (gimpfu.PF_BOOL, "crop_linked", "  Auto Crop Linked", False),
                    ],
                    [],
                    gimp_export)  # , menu, domain, on_query, on_run)

    gimpfu.register("python_fu_layout_import",
                    "Import Layers",
                    "Import layers from json and images",
                    "Nic", "Nicolas CORNETTE", "2014",
                    "Import Layout...",
                    "", [
                        (gimpfu.PF_DIRNAME, "import-path", "Import Path", DEFAULT_OUTPUT_DIR),
                    ],
                    [],
                    gimp_import, menu='<Image>/File/Export/')  # , domain, on_query, on_run)

    gimpfu.register("python_fu_layout_import_skin",
                    "Import Android Skin",
                    "Import Android Emulator Skin",
                    "Nic", "Nicolas CORNETTE", "2014",
                    "Import Emulator Skin...",
                    "", [
                        (gimpfu.PF_DIRNAME, "import-path", "Import Path", DEFAULT_OUTPUT_DIR),
                    ],
                    [],
                    gimp_import, menu='<Image>/File/Export/')  # , domain, on_query, on_run)

    gimpfu.main()

except ImportError:
    gimpfu, pdb = None, None
    print('Imported as a module \n')

if __name__ == '__main__':
    # Tests

    # Fake Gimp Layer
    class FakeLayer(object):
        def __init__(self, name, width, height):
            self.name = name
            self.width = width
            self.height = height

    # Fake Gimp Layer Group
    class FakeGroup(FakeLayer):
        def __init__(self, name, width, height, unsupported, layers):
            super(FakeGroup, self).__init__(name, width, height)
            self.unsupported = unsupported
            self.layers = layers

    assert as_ordered_dict(
            FakeLayer('n', 'w', 'h'), gimp_required_fields, gimp_extra_fields) == \
        OrderedDict([('name', 'n'), ('width', 'w'), ('height', 'h')])

    assert as_ordered_dict(
            FakeGroup('n', 'w', 'h', 'u', []), gimp_required_fields, gimp_extra_fields) == \
        OrderedDict([('name', 'n'), ('width', 'w'), ('height', 'h'), ('layers', [])])

    assert not as_ordered_dict(
        namedtuple('Foo', 'name')('foo'), gimp_required_fields, gimp_extra_fields)

    im = \
        FakeGroup("Image", 80, 60, False, [
            FakeLayer("layer_1", 80, 60),
            FakeLayer("Layer_2", 80, 60),
            FakeGroup("group_A", 80, 60, False, [
                FakeLayer("layer_A1", 80, 60),
                FakeLayer("Layer_A2", 80, 60)
            ])
        ])

    assert json.loads(json.dumps(im))
