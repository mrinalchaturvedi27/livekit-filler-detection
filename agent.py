"""
Main agent file for handling filler-word interruptions.
"""

import os
import re
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Any
from dotenv import load_dotenv

from livekit.agents import cli, WorkerOptions, JobContext, AgentSession

# Load .env file
load_dotenv()

# --- Plugin Imports ---
# Try to import plugins, but don't fail if they aren't installed.
# This lets the test harness run without all deps.
try:
    from livekit.plugins import deepgram, openai, cartesia, silero
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False
    logging.warning(
        "LiveKit plugins not installed. Agent will run in test mode only."
    )

logger = logging.getLogger(__name__)


class InterruptManager:
    """
    This class is responsible for filtering out "filler words" (like uh, um)
    when the agent is speaking. If the user says a real command
    (e.g., "umm... stop"), it extracts the command ("stop") and
    triggers an interruption.

    It ignores fillers *only* when the agent is mid-speech.
    If the agent is quiet, all user speech (including fillers)
    is processed normally.
    """

    def __init__(self, ignored_words: Optional[List[str]] = None):
        # Load filler words from env or use defaults
        self.ignored_words = set()
        self._load_fillers(ignored_words)

        # Load confidence threshold from .env
        default_conf = "0.6"
        try:
            self.confidence_threshold: float = float(
                os.getenv("CONFIDENCE_THRESHOLD", default_conf)
            )
        except ValueError:
            logging.warning(
                f"Invalid CONFIDENCE_THRESHOLD in .env. Defaulting to {default_conf}"
            )
            self.confidence_threshold = float(default_conf)

        logger.info(f"Confidence threshold set to {self.confidence_threshold}")

        self.is_speaking = False
        self._state_lock = asyncio.Lock()  # Protects is_speaking
        self.session: Optional[AgentSession] = None

    def _load_fillers(self, words_list: Optional[List[str]] = None):
        """Helper to load the set of ignored words."""
        env_fillers = os.getenv("IGNORED_WORDS")
        if env_fillers:
            words = [w.strip().lower() for w in env_fillers.split(",") if w.strip()]
            self.ignored_words = set(words)
        elif words_list:
            self.ignored_words = set(w.lower() for w in words_list)
        else:
            # Default filler words (English + Hindi)
            self.ignored_words = {
                "uh", "um", "umm", "hmm", "er", "ah",
                "like", "you know", "i mean", "well", "so",
                "haan", "matlab", "acchaa", "are"
            }
        logger.info(f"Ignoring filler words: {self.ignored_words}")

    def _is_just_filler(self, transcript: str) -> bool:
        """
        Checks if a transcript is *only* filler words.
        Returns True if no meaningful word is present.
        """
        words = [w for w in re.findall(r"\b\w+\b", transcript.lower())]
        if not words:
            return True  # Empty string is considered filler

        # TODO: maybe make the 3-word limit configurable in .env
        # Heuristic: don't classify long phrases as *only* filler
        if len(words) > 3:
            return False

        return all(word in self.ignored_words for word in words)

    def _extract_command(self, transcript: str) -> str:
        """
        Removes filler words to get the real command.
        e.g., "umm okay stop" -> "okay stop"
        """
        words = re.findall(r"\b\w+\b", transcript.lower())
        meaningful_words = [w for w in words if w not in self.ignored_words]
        return " ".join(meaningful_words)

    async def on_agent_state_changed(self, evt: Any) -> None:
        """
        Callback to track when the agent starts or stops speaking.
        """
        async with self._state_lock:
            # Handle both string and enum states
            new_state = (
                evt.new_state.value
                if hasattr(evt.new_state, "value")
                else evt.new_state
            )
            self.is_speaking = (str(new_state).lower() == "speaking")
            logger.debug(
                f"Agent state is now {new_state}, is_speaking={self.is_speaking}"
            )

    async def on_user_input_transcribed(self, evt: Any) -> None:
        """
        Main logic handler for incoming user speech.
        """
        # We only care about final transcripts
        if not getattr(evt, "is_final", False):
            return

        transcript = evt.transcript.strip()
        if not transcript:
            return

        confidence = getattr(evt, "confidence", 1.0)
        timestamp = datetime.utcnow().isoformat()

        # 1. Check confidence first
        if confidence < self.confidence_threshold:
            logger.info(
                f"(SKIP - Low Conf) '{transcript}', "
                f"conf={confidence:.2f}, time={timestamp}"
            )
            return

        # 2. Check agent state
        async with self._state_lock:
            if self.is_speaking:
                # Agent is speaking. Be selective about interruptions.
                if self._is_just_filler(transcript.lower()):
                    # It's *only* filler, ignore it
                    logger.info(
                        f"(IGNORE - Filler) '{transcript}', "
                        f"conf={confidence:.2f}, time={timestamp}"
                    )
                else:
                    # It's a mixed command or a real command.
                    cleaned_cmd = self._extract_command(transcript)

                    if cleaned_cmd:
                        # Got something real - interrupt!
                        logger.info(
                            f"[INTERRUPT] '{cleaned_cmd}' "
                            f"(from: '{transcript}'), "
                            f"conf={confidence:.2f}, time={timestamp}"
                        )
                        if self.session:
                            await self.session.interrupt()
                    else:
                        # e.g., "umm you know" - ended up being all filler
                        logger.info(
                            f"(IGNORE - All Fillers) '{transcript}', "
                            f"conf={confidence:.2f}, time={timestamp}"
                        )
            else:
                # Agent is quiet. Process everything.
                logger.info(
                    f"(NORMAL - Agent Idle) '{transcript}', "
                    f"conf={confidence:.2f}, time={timestamp}"
                )


async def entrypoint(job_ctx: JobContext) -> None:
    """
    Main entrypoint for the LiveKit agent job.
    """

    if not PLUGINS_AVAILABLE:
        logger.error("Required LiveKit plugins not found. Exiting.")
        logger.error(
            "Install with: pip install livekit-plugins-silero "
            "livekit-plugins-deepgram livekit-plugins-openai livekit-plugins-cartesia"
        )
        return

    # Setup the agent session with all the plugins
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-3"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=cartesia.TTS(),
        turn_detection="stt",
        allow_interruptions=True,
        min_interruption_duration=0.5,
        false_interruption_timeout=2.0,
    )

    # Create our custom logic handler
    interrupt_manager = InterruptManager()
    interrupt_manager.session = session

    # Wire up the event callbacks
    session.on("agent_state_changed")(interrupt_manager.on_agent_state_changed)
    session.on("user_input_transcribed")(
        interrupt_manager.on_user_input_transcribed
    )

    logger.info("Filler detection agent started successfully!")

    # Start the agent's main loop
    await session.run()


async def job_entrypoint(job_ctx: JobContext) -> None:
    """Called for each LiveKit job (when a participant joins)."""
    await entrypoint(job_ctx)


def run_test_harness():
    """
    Simulates the agent logic for testing without a LiveKit connection.
    """
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    print("=" * 80)
    print("Filler Detection Test Harness")
    print("=" * 80)
    print()
    
    # Create the manager we want to test
    interrupt_manager = InterruptManager()
    
    async def simulate():
        # Test cases: (transcript, confidence, agent_speaking, expected_result_note)
        test_cases = [
            # Original 10 tests
            ("um", 0.9, True, "IGNORE", "Filler only during agent speech"),
            ("uh hmm", 0.9, True, "IGNORE", "Multiple fillers"),
            ("stop", 0.9, True, "INTERRUPT", "Real command"),
            ("wait one second", 0.9, True, "INTERRUPT", "Full sentence command"),
            ("umm okay stop", 0.9, True, "INTERRUPT", "Mixed - extract 'okay stop'"),
            ("uh stop that", 0.9, True, "INTERRUPT", "Mixed - extract 'stop that'"),
            ("hello", 0.9, True, "INTERRUPT", "Valid greeting"),
            ("umm", 0.9, False, "NORMAL", "Filler when agent quiet"),
            ("hmm yeah", 0.3, True, "SKIP", "Low confidence"),
            ("", 0.9, True, "SKIP", "Empty transcript"),
            
            # More filler combinations
            ("um uh er", 0.9, True, "IGNORE", "Three fillers"),
            ("like you know", 0.9, True, "IGNORE", "Phrase fillers"),
            
            # More real commands
            ("hold on", 0.9, True, "INTERRUPT", "Hold on command"),
            ("wait", 0.9, True, "INTERRUPT", "Single word wait"),
            ("no", 0.9, True, "INTERRUPT", "Disagreement"),
            ("yes", 0.9, True, "INTERRUPT", "Agreement"),
            ("actually", 0.9, True, "INTERRUPT", "Correction"),
            
            # More mixed commands
            ("um wait please", 0.9, True, "INTERRUPT", "Mixed with please"),
            ("uh no stop", 0.9, True, "INTERRUPT", "Multiple commands"),
            ("hmm I disagree", 0.9, True, "INTERRUPT", "Filler + statement"),
            
            # Hindi tests
            ("haan stop", 0.9, True, "INTERRUPT", "Hindi filler + English command"),
            ("matlab wait", 0.9, True, "INTERRUPT", "Hindi filler mixed"),
            ("acchaa", 0.9, True, "IGNORE", "Hindi filler only"),
            
            # Confidence variations
            ("stop", 0.5, True, "SKIP", "Borderline confidence"),
            ("wait", 0.8, True, "INTERRUPT", "Good confidence"),
            ("um", 0.4, True, "SKIP", "Low confidence filler"),
            
            # Agent quiet scenarios
            ("hello", 0.9, False, "NORMAL", "Greeting when quiet"),
            ("um I think", 0.9, False, "NORMAL", "Mixed when quiet"),
            ("stop", 0.9, False, "NORMAL", "Command when quiet"),
            
            # Edge cases
            ("     ", 0.9, True, "SKIP", "Only spaces"),
            ("um um um um", 0.9, True, "IGNORE", "Many fillers (>3 words)"),
            ("well so like", 0.9, True, "IGNORE", "All different fillers"),
        ]
        
        # Mock event class
        class MockEvent:
            def __init__(self, transcript, confidence, is_final=True):
                self.transcript = transcript
                self.is_final = is_final
                self.confidence = confidence
        
        total_tests = len(test_cases)
        
        # IMPORTANT: This for loop must be indented inside the simulate() function
        for i, (transcript, conf, is_speaking, expected, description) in enumerate(test_cases, 1):
            # Set the mock state
            interrupt_manager.is_speaking = is_speaking
            event = MockEvent(transcript, conf, is_final=True)
            
            print(f"\n--- Test {i}/{total_tests} (Expected: {expected}) ---")
            print(f"Description: {description}")
            print(f"Input: \"{transcript}\"")
            print(f"Agent Speaking: {'Yes' if is_speaking else 'No'}")
            print(f"Confidence: {conf:.2f}")
            print("Result Log: ", end="")
            
            # Run the handler
            await interrupt_manager.on_user_input_transcribed(event)
        
        print("\n" + "=" * 80)
        print(f"Test Summary: {total_tests}/{len(test_cases)} scenarios executed.")
        print("=" * 80)
    
    # IMPORTANT: This should be at the end of run_test_harness(), NOT inside simulate()
    asyncio.run(simulate())


if __name__ == "__main__":
    import sys

    # Basic logging config
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Check for 'test' argument
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("\nRunning test harness...\n")
        run_test_harness()
    else:
        # Run the agent normally
        cli.run_app(
            WorkerOptions(
                entrypoint_fnc=job_entrypoint,
            )
        )