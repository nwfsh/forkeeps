import { Image } from 'expo-image';
import * as MediaLibrary from 'expo-media-library';
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

import { usePhotos } from '@/components/photos-provider';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import type { Photo } from '@/lib/photos';

const COLUMNS = 3;
const GAP = 2;

export default function PhotosScreen() {
  const { photos } = usePhotos();
  const { width } = useWindowDimensions();
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const size = (width - GAP * (COLUMNS - 1)) / COLUMNS;

  return (
    <ThemedView style={styles.fill}>
      <SafeAreaView style={styles.fill} edges={['top']}>
        <ThemedText type="subtitle" style={styles.header}>
          {photos.length} photo{photos.length === 1 ? '' : 's'}
        </ThemedText>
        {photos.length === 0 ? (
          <ThemedText style={styles.empty}>Photos you take on the Camera tab show up here.</ThemedText>
        ) : (
          <FlatList
            data={photos}
            keyExtractor={(p) => p.id}
            numColumns={COLUMNS}
            columnWrapperStyle={{ gap: GAP }}
            contentContainerStyle={{ gap: GAP, paddingBottom: BottomTabInset + Spacing.three }}
            renderItem={({ item, index }) => (
              <Pressable onPress={() => setOpenIndex(index)}>
                <Image source={{ uri: item.uri }} style={{ width: size, height: size }} contentFit="cover" />
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
  const { remove } = usePhotos();
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
    }
  }

  function confirmDelete() {
    if (!current) return;
    Alert.alert('Delete photo?', undefined, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          remove(current.id);
          if (photos.length === 1) onClose();
          else setIndex((i) => Math.min(i, photos.length - 2));
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
            <Image source={{ uri: item.uri }} style={{ width, height: '100%' }} contentFit="contain" />
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
  header: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.three,
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
