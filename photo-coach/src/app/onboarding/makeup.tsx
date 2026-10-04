import { MakeupLookScreen } from '@/components/makeup-look';
import { useOnboarding } from '@/components/onboarding-provider';

/** Onboarding's last, optional step: the makeup look to keep an eye on. */
export default function OnboardingMakeupScreen() {
  const { finish } = useOnboarding();
  return <MakeupLookScreen doneLabel="Start coaching" onDone={finish} />;
}
