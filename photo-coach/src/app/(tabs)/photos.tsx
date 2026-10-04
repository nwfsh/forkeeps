import { Image } from 'expo-image';
import * as MediaLibrary from 'expo-media-library';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Pressable,
  SectionList,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useOnboarding } from '@/components/onboarding-provider';
import { usePhotos } from '@/components/photos-provider';
import { RetrainBanner } from '@/components/retrain-banner';
import { INK, MUTED } from '@/components/onboarding-style';
import { BottomTabInset, Spacing } from '@/constants/theme';
import type { Photo } from '@/lib/photos';
import { sendVerdict } from '@/lib/server';

const COLUMNS = 3;
const GAP = 6;
const SIDE = 16;

/** "24 FEB 2026": the day a photo was taken, as the grid's section heading. */
function dayLabel(takenAt: number) {
  return new Date(takenAt)
    .toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    .toUpperCase();
}

/** The photos grouped by day, newest first, each day cut into rows of COLUMNS. */
function byDay(photos: Photo[]) {
  const days: { title: string; photos: Photo[] }[] = [];
  for (const photo of [...photos].sort((a, b) => b.takenAt - a.takenAt)) {
    const title = dayLabel(photo.takenAt);
    if (days.at(-1)?.title !== title) days.push({ title, photos: [] });
    days.at(-1)!.photos.push(photo);
  }
  return days.map((day) => ({
    title: day.title,
    data: Array.from({ length: Math.ceil(day.photos.length / COLUMNS) }, (_, i) =>
      day.photos.slice(i * COLUMNS, (i + 1) * COLUMNS),
    ),
  }));
}

export default function PhotosScreen() {
  const { photos: all } = usePhotos();
  const { restart } = useOnboarding();
  // Burst shots that weren't the best wait in review; they join the grid once kept.
  const photos = all.filter((p) => !p.alternate || p.kept);
  const { width } = useWindowDimensions();
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const size = (width - SIDE * 2 - GAP * (COLUMNS - 1)) / COLUMNS;
  const toReview = all.filter((p) => !p.kept).length;
  // The viewer pages through the photos in the grid's order.
  const sections = byDay(photos);
  const ordered = sections.flatMap((section) => section.data.flat());

  const header = (
    <View style={styles.header}>
      <View style={styles.titleRow}>
        <View style={styles.titleText}>
          <Text style={styles.title}>Photo gallery</Text>
          <Text style={styles.count}>
            {photos.length} photo{photos.length === 1 ? '' : 's'}
          </Text>
        </View>
        <View style={styles.headerButtons}>
          {/* Swipe the photos the coach is least sure about, then retrain the model you have. */}
          {photos.length > 1 && (
            <Pressable style={styles.outlineButton} onPress={() => router.push('/tune')}>
              <Text style={styles.outlineText}>Tune</Text>
            </Pressable>
          )}
          {toReview > 0 && (
            <Pressable style={styles.inkButton} onPress={() => router.push('/review')}>
              <Text style={styles.inkText}>Review {toReview}</Text>
            </Pressable>
          )}
        </View>
      </View>
      <RetrainBanner />
      <View style={styles.links}>
        <Pressable accessibilityRole="button" onPress={() => restart()} hitSlop={8}>
          <Text style={styles.link}>Replay intro</Text>
        </Pressable>
        {/* Every onboarding page with a Skip button, for checking the design quickly. */}
        <Pressable accessibilityRole="button" onPress={() => restart(true)} hitSlop={8}>
          <Text style={styles.link}>Preview screens</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => router.push('/makeup')} hitSlop={8}>
          <Text style={styles.link}>Makeup look</Text>
        </Pressable>
      </View>
    </View>
  );

  return (
    <View style={styles.fill}>
      <SafeAreaView style={styles.fill} edges={['top']}>
        <SectionList
          sections={sections}
          keyExtractor={(row) => row[0].id}
          ListHeaderComponent={header}
          ListEmptyComponent={
            <Text style={styles.empty}>Photos you take on the Camera tab show up here.</Text>
          }
          stickySectionHeadersEnabled={false}
          contentContainerStyle={{ paddingBottom: BottomTabInset + Spacing.four }}
          renderSectionHeader={({ section }) => <Text style={styles.day}>{section.title}</Text>}
          renderItem={({ item: row }) => (
            <View style={styles.row}>
              {row.map((photo) => (
                <Pressable
                  key={photo.id}
                  accessibilityRole="button"
                  accessibilityLabel="Open photo"
                  onPress={() => setOpenIndex(ordered.indexOf(photo))}>
                  <Image
                    source={{ uri: photo.uri }}
                    style={[styles.tile, { width: size, height: size }]}
                    contentFit="cover"
                  />
                </Pressable>
              ))}
            </View>
          )}
        />
      </SafeAreaView>

      {openIndex !== null && (
        <Viewer photos={ordered} initialIndex={openIndex} onClose={() => setOpenIndex(null)} />
      )}
    </View>
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
        <SafeAreaView style={styles.viewerHud} edges={['top', 'bottom']} pointerEvents="box-none">
          <View style={styles.viewerTop}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Back to the gallery"
              onPress={onClose}
              hitSlop={8}
              style={styles.back}>
              <SymbolView
                name={{ ios: 'chevron.left', android: 'arrow_back', web: 'arrow_back' }}
                size={18}
                weight="semibold"
                tintColor="#FFFFFF"
              />
            </Pressable>
            <Text style={styles.viewerText}>
              {index + 1} / {photos.length}
            </Text>
          </View>
          {/* Delete and save as two separate buttons at the bottom. */}
          <View style={styles.actionFrame}>
            <Pressable
              accessibilityRole="button"
              onPress={confirmDelete}
              style={({ pressed }) => [styles.action, pressed && styles.actionPressed]}>
              <SymbolView
                name={{ ios: 'trash', android: 'delete', web: 'delete' }}
                size={18}
                tintColor="#F87171"
              />
              <Text style={[styles.actionText, styles.danger]}>Delete</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={save}
              style={({ pressed }) => [styles.action, pressed && styles.actionPressed]}>
              <SymbolView
                name={{ ios: 'square.and.arrow.down', android: 'download', web: 'download' }}
                size={18}
                tintColor="#FFFFFF"
              />
              <Text style={styles.actionText}>Save to Photos</Text>
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
    backgroundColor: '#FFFFFF',
  },
  header: {
    paddingHorizontal: SIDE,
    paddingTop: 24,
    paddingBottom: 8,
    gap: 12,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  titleText: {
    flexShrink: 1,
    gap: 4,
  },
  title: {
    color: INK,
    fontSize: 32,
    lineHeight: 38,
    fontWeight: '700',
    letterSpacing: -0.5,
  },
  count: {
    color: MUTED,
    fontSize: 16,
  },
  headerButtons: {
    flexDirection: 'row',
    gap: 8,
    paddingTop: 4,
  },
  outlineButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: INK,
  },
  outlineText: {
    color: INK,
    fontWeight: '600',
  },
  inkButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: INK,
  },
  inkText: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  links: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  link: {
    color: MUTED,
    fontSize: 13,
  },
  day: {
    color: MUTED,
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.6,
    paddingHorizontal: SIDE,
    paddingTop: 20,
    paddingBottom: 10,
    backgroundColor: '#FFFFFF',
  },
  row: {
    flexDirection: 'row',
    gap: GAP,
    paddingHorizontal: SIDE,
    marginBottom: GAP,
  },
  tile: {
    backgroundColor: '#EEE9E6',
  },
  empty: {
    color: MUTED,
    fontSize: 16,
    paddingHorizontal: SIDE,
    paddingTop: 16,
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
  back: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionFrame: {
    flexDirection: 'row',
    gap: 12,
    marginHorizontal: 20,
    marginBottom: 40,
  },
  action: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    height: 52,
    borderRadius: 999,
    backgroundColor: 'rgba(30,30,30,0.85)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  actionPressed: {
    backgroundColor: 'rgba(60,60,60,0.9)',
  },
  actionText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  viewerText: {
    color: '#fff',
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  danger: {
    color: '#F87171',
  },
});
