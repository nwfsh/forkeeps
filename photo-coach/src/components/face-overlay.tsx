import { StyleSheet, View } from 'react-native';

import type { Analysis } from '@/lib/server';

type Props = {
  analysis: Analysis;
  /** Size of the camera preview on screen. */
  viewWidth: number;
  viewHeight: number;
  /** The front-camera preview is mirrored but the photo isn't, so flip boxes to match. */
  mirrored: boolean;
};

/**
 * Draws a box over each detected face. The preview fills the screen ("cover"),
 * so the photo is scaled up and its overflow cropped; boxes get the same transform.
 */
export function FaceOverlay({ analysis, viewWidth, viewHeight, mirrored }: Props) {
  const scale = Math.max(viewWidth / analysis.width, viewHeight / analysis.height);
  const offsetX = (viewWidth - analysis.width * scale) / 2;
  const offsetY = (viewHeight - analysis.height * scale) / 2;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {analysis.faces.map((face, i) => {
        const x = mirrored ? 1 - face.bbox.x - face.bbox.w : face.bbox.x;
        return (
          <View
            key={i}
            style={[
              styles.box,
              face.cut_off && styles.cutOff,
              {
                left: offsetX + x * analysis.width * scale,
                top: offsetY + face.bbox.y * analysis.height * scale,
                width: face.bbox.w * analysis.width * scale,
                height: face.bbox.h * analysis.height * scale,
              },
            ]}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    position: 'absolute',
    borderWidth: 2,
    borderRadius: 12,
    borderColor: '#4ADE80',
  },
  cutOff: {
    borderColor: '#F87171',
  },
});
