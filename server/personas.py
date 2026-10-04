"""The coach's voices: who they are, how they sound and what each one says for every tip.

The tips are a small fixed set, so every line is recorded once by generate_voices.py and
served as an mp3, rather than calling ElevenLabs while someone is taking a photo.
"""
from pathlib import Path

VOICES_FOLDER = Path(__file__).resolve().parent / "voices"
# Good for expressive short lines; speed doesn't matter because clips are made ahead of time.
MODEL = "eleven_multilingual_v2"

# Every line the coach can say. Warnings from vision.framing_warnings carry one of these as
# their "clip"; looks_good is what the app plays when there are no warnings.
CLIPS = (
    "no_person",
    "cut_off_left", "cut_off_right", "cut_off_top", "cut_off_bottom",
    "cut_at_joint_ankles", "cut_at_joint_knees", "cut_at_joint_hips",
    "looking_room_left", "looking_room_right",
    "too_close",
    "looks_good",
)

# voice_id picks the sound (see `python generate_voices.py --voices` for what your account has).
# settings shape the delivery: lower stability is more emotional, style exaggerates the voice's
# character, speed is 0.7-1.2. The lines carry the attitude.
PERSONAS = {
    "hype": {
        "name": "Hype man",
        "description": "Loud, excited, thinks every shot is the one",
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "settings": {"stability": 0.3, "similarity_boost": 0.75, "style": 0.6, "speed": 1.1},
        "lines": {
            "no_person": "Yo, where'd you go? Get in the frame!",
            "cut_off_left": "Hold up, you're falling off the left! Slide back in!",
            "cut_off_right": "Hold up, you're falling off the right! Slide back in!",
            "cut_off_top": "We're losing the top of your head! Tilt it up, tilt it up!",
            "cut_off_bottom": "Your face is dropping out the bottom! Bring it up!",
            "cut_at_joint_ankles": "Don't chop those ankles! Show the whole look, shoes and all!",
            "cut_at_joint_knees": "Not at the knees! Go wider or go tighter, let's go!",
            "cut_at_joint_hips": "Right at the hips? Nah! Shift it up or down, you got this!",
            "looking_room_left": "Give yourself some room on the left! Let that look breathe!",
            "looking_room_right": "Give yourself some room on the right! Let that look breathe!",
            "too_close": "Whoa, back it up a little! Give me that full look!",
            "looks_good": "Yes! That's the one! Take it, take it!",
        },
    },
    "strict": {
        "name": "Strict",
        "description": "Short, stern, not here to flatter you",
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "settings": {"stability": 0.75, "similarity_boost": 0.75, "style": 0.1, "speed": 1.0},
        "lines": {
            "no_person": "Nobody in frame. Fix it.",
            "cut_off_left": "Cut off on the left. Move.",
            "cut_off_right": "Cut off on the right. Move.",
            "cut_off_top": "Top of the head is cut off. Tilt up.",
            "cut_off_bottom": "Face is cut off at the bottom. Tilt down.",
            "cut_at_joint_ankles": "Never crop at the ankles. Reframe.",
            "cut_at_joint_knees": "Never crop at the knees. Reframe.",
            "cut_at_joint_hips": "Never crop at the hips. Reframe.",
            "looking_room_left": "More space on the left. Now.",
            "looking_room_right": "More space on the right. Now.",
            "too_close": "Too close. Step back.",
            "looks_good": "Acceptable. Take the photo.",
        },
    },
    "sunny": {
        "name": "Sunny",
        "description": "A warm, encouraging woman's voice",
        "voice_id": "cgSgspJ2msm6clMCkdW9",
        "settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3, "speed": 1.0},
        "lines": {
            "no_person": "I can't see anyone yet. Step into the frame when you're ready.",
            "cut_off_left": "You're slipping out on the left. Come back in a little.",
            "cut_off_right": "You're slipping out on the right. Come back in a little.",
            "cut_off_top": "The top of your head is cut off. Tilt the camera up a touch.",
            "cut_off_bottom": "Your face is cut off at the bottom. Tilt the camera down a touch.",
            "cut_at_joint_ankles": "The frame ends right at your ankles. Try showing your feet too.",
            "cut_at_joint_knees": "The frame ends right at your knees. A little wider or tighter will look better.",
            "cut_at_joint_hips": "The frame ends right at your hips. A little higher or lower will look better.",
            "looking_room_left": "Leave a bit more space on the left, where you're looking.",
            "looking_room_right": "Leave a bit more space on the right, where you're looking.",
            "too_close": "You're a little close. Take a small step back.",
            "looks_good": "That looks lovely. Go ahead.",
        },
    },
    "chill": {
        "name": "Chill",
        "description": "A calm, laid-back man's voice",
        "voice_id": "bIHbv24MWmeRgasZH58o",
        "settings": {"stability": 0.6, "similarity_boost": 0.75, "style": 0.2, "speed": 0.95},
        "lines": {
            "no_person": "Can't see anyone. Whenever you're ready.",
            "cut_off_left": "You're drifting off the left side. Ease back in.",
            "cut_off_right": "You're drifting off the right side. Ease back in.",
            "cut_off_top": "Losing the top of your head. Tilt up a bit.",
            "cut_off_bottom": "Your face is dipping out the bottom. Tilt down a bit.",
            "cut_at_joint_ankles": "It's cutting at the ankles. Get the feet in.",
            "cut_at_joint_knees": "It's cutting at the knees. Go a bit wider or tighter.",
            "cut_at_joint_hips": "It's cutting at the hips. Nudge it up or down.",
            "looking_room_left": "Bit more room on the left, where you're looking.",
            "looking_room_right": "Bit more room on the right, where you're looking.",
            "too_close": "Little close. Take a step back.",
            "looks_good": "Yeah, that works. Take it.",
        },
    },
}


def clip_path(persona: str, clip: str) -> Path:
    """Where a persona's recording of one line is kept."""
    return VOICES_FOLDER / persona / f"{clip}.mp3"


def recorded(persona: str) -> list[str]:
    """The clips that have been generated for this persona."""
    return [clip for clip in CLIPS if clip_path(persona, clip).exists()]
