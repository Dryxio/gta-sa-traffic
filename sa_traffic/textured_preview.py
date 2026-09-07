"""Render an existing traffic .blend with unlit textures and diagnostic overlays.

Blender --background context.blend --python-exit-code 1 --python THIS_FILE --
  --render /absolute/new-preview.png [--output /absolute/new-preview.blend]

This is a diagnostic rendering policy, not the game's lighting or traffic simulation.
"""
import argparse
from pathlib import Path
import sys


def prepare(scene):
    import bpy
    replacements = {}
    for obj in scene.objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            key = material.as_pointer()
            if key not in replacements:
                clone = material.copy()
                clone.name = material.name + ' [traffic textured preview]'
                clone.use_nodes = True
                tree = clone.node_tree
                texture = next((node for node in tree.nodes
                                if node.type == 'TEX_IMAGE' and node.image), None)
                output = next((node for node in tree.nodes
                               if node.type == 'OUTPUT_MATERIAL' and node.is_active_output), None)
                if output is None:
                    output = tree.nodes.new('ShaderNodeOutputMaterial')
                emission = tree.nodes.new('ShaderNodeEmission')
                emission.inputs['Color'].default_value = material.diffuse_color
                if texture:
                    tree.links.new(texture.outputs['Color'], emission.inputs['Color'])
                    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
                    mix = tree.nodes.new('ShaderNodeMixShader')
                    tree.links.new(texture.outputs['Alpha'], mix.inputs[0])
                    tree.links.new(transparent.outputs[0], mix.inputs[1])
                    tree.links.new(emission.outputs[0], mix.inputs[2])
                    tree.links.new(mix.outputs[0], output.inputs['Surface'])
                else:
                    tree.links.new(emission.outputs[0], output.inputs['Surface'])
                replacements[key] = clone
            # Object-local override avoids modifying meshes shared outside this scene.
            slot.link = 'OBJECT'
            slot.material = replacements[key]
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    return len(replacements)


def main(argv=None):
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', required=True)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    image_path = Path(args.render).resolve()
    blend_path = Path(args.output).resolve() if args.output else None
    paths = [image_path] + ([blend_path] if blend_path else [])
    if len(set(paths)) != len(paths):
        raise ValueError('OUTPUT_COLLISION: image and blend must differ')
    for path in paths:
        if path.exists():
            raise ValueError('OUTPUT_EXISTS: preview requires fresh output paths: ' + str(path))
    if not bpy.context.scene.camera:
        raise ValueError('CAMERA_REQUIRED: create a diagnostic camera with blender_bridge first')
    prepare(bpy.context.scene)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(image_path)
    if blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
