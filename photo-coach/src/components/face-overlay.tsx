import { StyleSheet, Text, View } from 'react-native';

import type { Analysis } from '@/lib/server';
import { ACCENT } from '@/components/onboarding-style';
import { FontFamily } from '@/constants/theme';

type Props = {
  analysis: Analysis;
  /** Size of the camera preview on screen. */
  viewWidth: number;
  viewHeight: number;
  /** The front-camera preview is mirrored but the photo isn't, so flip boxes to match. */
  mirrored: boolean;
};

/**
 * Draws a box over each detected face, with the person's name above it when the server
 * recognises them. The preview fills the screen ("cover"), so the photo is scaled up and
 * its overflow cropped; boxes get the same transform.
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
            ]}>
            {face.name && (
              <Text style={[styles.name, face.cut_off && styles.nameCutOff]} numberOfLines={1}>
                {face.name}
              </Text>
            )}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    position: 'absolute',
    borderWidth: 3,
    borderRadius: 12,
    // The brand's dark pink; a face cut off by the edge turns red instead.
    borderColor: ACCENT,
  },
  cutOff: {
    borderColor: '#F87171',
  },
  name: {
    fontFamily: FontFamily.bodyBold,
    position: 'absolute',
    bottom: '100%',
    left: -2,
    marginBottom: 4,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: ACCENT,
    color: '#FFFFFF',
    fontSize: 13,
    textTransform: 'capitalize',
  },
  nameCutOff: {
    backgroundColor: '#F87171',
    color: '#450a0a',
  },
});
