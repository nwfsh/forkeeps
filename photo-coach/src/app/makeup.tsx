import { router } from 'expo-router';

import { MakeupLookScreen } from '@/components/makeup-look';

/** Setting or changing the makeup look after onboarding, from the Photos tab. */
export default function MakeupScreen() {
  return <MakeupLookScreen doneLabel="Done" onDone={() => router.back()} />;
}
