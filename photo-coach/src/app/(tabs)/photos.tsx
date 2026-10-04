import { Image } from 'expo-image';
import * as MediaLibrary from 'expo-media-library';
import { router } from 'expo-router';
import { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import { usePhotos } from '@/components/photos-provider';
import { RetrainBanner } from '@/components/retrain-banner';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import type { Photo } from '@/lib/photos';
import { sendVerdict } from '@/lib/server';

const COLUMNS = 3;
const GAP = 2;

export default function PhotosScreen() {
  const { photos: all } = usePhotos();
  const { restart } = useOnboarding();
  // Burst shots that weren't the best wait in review; they join the grid once kept.
  const photos = all.filter((p) => !p.alternate || p.kept);
  const { width } = useWindowDimensions();
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const size = (width - GAP * (COLUMNS - 1)) / COLUMNS;
  const toReview = all.filter((p) => !p.kept).length;

  return (
    <ThemedView style={styles.fill}>
      <SafeAreaView style={styles.fill} edges={['top']}>
        <View style={styles.headerRow}>
          <ThemedText type="subtitle">
            {photos.length} photo{photos.length === 1 ? '' : 's'}
          </ThemedText>
          <View style={styles.headerButtons}>
            {/* Swipe the photos the coach is least sure about, then retrain the model you have. */}
            {photos.length > 1 && (
              <Pressable style={styles.tuneButton} onPress={() => router.push('/tune')}>
                <Text style={styles.tuneText}>Tune</Text>
              </Pressable>
            )}
            {toReview > 0 && (
              <Pressable style={styles.reviewButton} onPress={() => router.push('/review')}>
                <Text style={styles.reviewText}>Review {toReview}</Text>
              </Pressable>
            )}
          </View>
        </View>
        <RetrainBanner />
        <View style={styles.replayRow}>
          <Pressable accessibilityRole="button" onPress={() => restart()} hitSlop={8}>
            <ThemedText type="small" themeColor="textSecondary">
              Replay intro
            </ThemedText>
          </Pressable>
          {/* Every onboarding page with a Skip button, for checking the design quickly. */}
          <Pressable accessibilityRole="button" onPress={() => restart(true)} hitSlop={8}>
            <ThemedText type="small" themeColor="textSecondary">
              Preview screens
            </ThemedText>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/makeup')} hitSlop={8}>
            <ThemedText type="small" themeColor="textSecondary">
              Makeup look
            </ThemedText>
          </Pressable>
        </View>
        {photos.length === 0 ? (
          <ThemedText style={styles.empty}>
            Photos you take on the Camera tab show up here.
          </ThemedText>
        ) : (
          <FlatList
            data={photos}
            keyExtractor={(p) => p.id}
            numColumns={COLUMNS}
            columnWrapperStyle={{ gap: GAP }}
            contentContainerStyle={{ gap: GAP, paddingBottom: BottomTabInset + Spacing.three }}
            renderItem={({ item, index }) => (
              <Pressable onPress={() => setOpenIndex(index)}>
                <Image
                  source={{ uri: item.uri }}
                  style={{ width: size, height: size }}
                  contentFit="cover"
                />
              </Pressable>
            )}
          />
        )}
      </SafeAreaView>

      {openIndex !== null && (
        <Viewer photos={photos} initialIndex={openIndex} onClose={() => setOpenIndex(null)} />
      )}
    </ThemedView>
  );
}

function Viewer({
  photos,
  initialIndex,
  onClose,
}: {
  photos: Photo[];
  initialIndex: number;
  onClose: () => void;
}) {
  const { remove, keep } = usePhotos();
  const { width } = useWindowDimensions();
  const [index, setIndex] = useState(initialIndex);
  const [permission, requestPermission] = MediaLibrary.usePermissions({ writeOnly: true });
  const current = photos[index];

  async function save() {
    if (!current) return;
    const granted = permission?.granted || (await requestPermission()).granted;
    if (!granted) {
      Alert.alert('No access', 'Allow Photos access in Settings to save pictures.');
      return;
    }
    try {
      await MediaLibrary.Asset.create(current.uri);
      Alert.alert('Saved', 'Added to your Photos library.');
    } catch (e) {
      Alert.alert('Save failed', e instanceof Error ? e.message : String(e));
      return;
    }
    // Saving a photo says you like it, the same as keeping it in review. The photo is safely
    // saved either way, so a server that can't be reached only costs this one vote.
    sendVerdict(current.id, 'keep', current.analysis)
      .then(() => keep(current.id))
      .catch((e) => console.warn(`Couldn't record keeping photo ${current.id}`, e));
  }

  function deleteNow(photo: Photo) {
    remove(photo.id);
    if (photos.length === 1) onClose();
    else setIndex((i) => Math.min(i, photos.length - 2));
  }

  function confirmDelete() {
    if (!current) return;
    const photo = current;
    Alert.alert('Delete photo?', undefined, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          // The vote is saved first, like in review, since the photo can't come back after.
          try {
            await sendVerdict(photo.id, 'remove', photo.analysis);
            deleteNow(photo);
          } catch {
            Alert.alert(
              "Couldn't reach the server",
              "Delete anyway? This photo won't count toward your taste.",
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete anyway', style: 'destructive', onPress: () => deleteNow(photo) },
              ],
            );
          }
        },
      },
    ]);
  }

  return (
    <Modal visible animationType="fade" onRequestClose={onClose}>
      <View style={styles.viewer}>
        <FlatList
          data={photos}
          keyExtractor={(p) => p.id}
          horizontal
          pagingEnabled
          initialScrollIndex={initialIndex}
          getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
          onMomentumScrollEnd={(e) => setIndex(Math.round(e.nativeEvent.contentOffset.x / width))}
          renderItem={({ item }) => (
            <Image
              source={{ uri: item.uri }}
              style={{ width, height: '100%' }}
              contentFit="contain"
            />
          )}
        />
        <SafeAreaView style={styles.viewerHud} pointerEvents="box-none">
          <View style={styles.viewerTop}>
            <Text style={styles.viewerText}>
              {index + 1} / {photos.length}
            </Text>
            <Pressable style={styles.pill} onPress={onClose}>
              <Text style={styles.pillText}>Done</Text>
            </Pressable>
          </View>
          <View style={styles.viewerBottom}>
            <Pressable style={styles.pill} onPress={confirmDelete}>
              <Text style={[styles.pillText, styles.danger]}>Delete</Text>
            </Pressable>
            <Pressable style={styles.pill} onPress={save}>
              <Text style={styles.pillText}>Save to Photos</Text>
            </Pressable>
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  headerButtons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  tuneButton: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: '#3DDC84',
  },
  tuneText: {
    color: '#3DDC84',
    fontWeight: '700',
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.three,
  },
  replayRow: {
    flexDirection: 'row',
    gap: Spacing.four,
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  reviewButton: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: '#3DDC84',
  },
  reviewText: {
    color: '#0B2E19',
    fontWeight: '700',
  },
  empty: {
    paddingHorizontal: Spacing.three,
  },
  viewer: {
    flex: 1,
    backgroundColor: '#000',
  },
  viewerHud: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'space-between',
  },
  viewerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.three,
  },
  viewerBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: Spacing.three,
  },
  viewerText: {
    color: '#fff',
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  pill: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  pillText: {
    color: '#fff',
    fontWeight: '600',
  },
  danger: {
    color: '#F87171',
  },
});
