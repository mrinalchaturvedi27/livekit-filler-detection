# LiveKit Filler Detection Agent

## What It Does
Intelligently filters filler words ("um", "uh", "hmm") when the agent is speaking, while still catching real interruptions. Also handles mixed commands - extracts "okay stop" from "umm okay stop".

## Quick Test
No setup needed:
```bash
python agent3.py test
```

**Expected Output:**
```
Test Summary: 33/33 scenarios executed
[INTERRUPT] Valid commands extracted from mixed input
(IGNORE - Filler) Pure filler words during agent speech
(NORMAL - Agent Idle) All input processed when agent quiet
```

## Features
✅ Context-aware filtering (agent speaking vs quiet)
✅ Mixed command extraction ("umm okay stop" → "okay stop")  
✅ Confidence-based filtering (ignores low-confidence background noise)
✅ Multi-language support (English + Hindi fillers)
✅ Environment-based configuration
✅ Comprehensive logging with timestamps
✅ Edge case handling (empty strings, multiple fillers, phrase detection)
✅ Extended test suite (33 test cases covering all scenarios)

## Setup

### 1. Install Dependencies
```bash
pip install livekit-agents livekit-plugins-silero
pip install livekit-plugins-deepgram livekit-plugins-openai livekit-plugins-cartesia
pip install python-dotenv
```

### 2. Configure
```bash
cp .env.template .env
# Edit .env with your API keys
```

### 3. Run
```bash
python agent3.py dev
```

## Configuration
Edit `.env` file:
- `IGNORED_WORDS`: Comma-separated list of filler words (default: "uh,um,umm,hmm,er,ah,like,you know,i mean,well,so,haan,matlab,acchaa,are")
- `CONFIDENCE_THRESHOLD`: Minimum confidence (0.0-1.0, default 0.6)

## How It Works

1. **No VAD modifications** - Uses LiveKit's event system
2. **Context-aware** - Different behavior when agent speaking vs quiet
3. **Smart extraction** - Removes fillers from mixed commands
4. **Confidence filtering** - Ignores low-quality transcriptions
5. **Heuristic-based** - Phrases >3 words not classified as pure filler

## Architecture
```
User Speech → STT → Transcription Event
                         ↓
              Confidence Check (≥0.6)
                         ↓
              Agent State Check
                 /           \
           Speaking        Quiet
                ↓            ↓
         Filler Filter   Normal Input
                ↓
         Extract Command
                ↓
         Interrupt Agent
```

## Test Results

All 33 test scenarios pass covering:

### Original 10 Core Tests
- ✅ Pure fillers ignored ("um", "uh hmm")
- ✅ Real commands interrupt ("stop", "wait one second")
- ✅ Mixed commands extracted ("umm okay stop" → "okay stop")
- ✅ Context-aware (fillers processed when agent quiet)
- ✅ Low confidence filtered
- ✅ Empty input handling

### Additional 23 Extended Tests
- ✅ Multiple filler combinations ("um uh er", "like you know")
- ✅ Various real commands ("hold on", "wait", "no", "yes", "actually")
- ✅ Complex mixed commands ("um wait please", "hmm I disagree")
- ✅ Hindi filler support ("haan stop", "matlab wait", "acchaa")
- ✅ Confidence edge cases (0.4, 0.5, 0.8 thresholds)
- ✅ Agent quiet scenarios (greetings, mixed input, commands)
- ✅ Edge cases (whitespace, 4+ fillers, phrase detection)

## Key Implementation Details

### InterruptManager Class
- **Thread-safe state management**: Uses `asyncio.Lock()` to protect `is_speaking` state
- **Configurable filler words**: Loads from environment or uses defaults
- **Smart command extraction**: Regex-based word filtering
- **Heuristic filtering**: Phrases >3 words not considered pure filler

### Event Handlers
- `on_agent_state_changed()`: Tracks agent speaking/quiet state
- `on_user_input_transcribed()`: Main logic for processing transcriptions

### Logging Categories
- `(SKIP - Low Conf)`: Below confidence threshold
- `(IGNORE - Filler)`: Pure filler during agent speech
- `[INTERRUPT]`: Valid command triggering interruption
- `(IGNORE - All Fillers)`: Mixed input that resolved to all fillers
- `(NORMAL - Agent Idle)`: Any input when agent quiet

## Technical Details

- **Language**: Python 3.10+
- **Framework**: LiveKit Agents SDK
- **Event-driven**: Async/await with thread-safe state management
- **Configuration**: Environment variables via .env file
- **Logging**: Structured logs with timestamps and confidence scores
- **Testing**: Built-in test harness with 33 scenarios

## Challenge Requirements Met

✅ Ignore fillers when agent speaking
✅ Register fillers when agent quiet  
✅ Real-time responsiveness
✅ No VAD modifications
✅ Configurable parameters
✅ Async/thread-safe
✅ Comprehensive logging
✅ Dynamic word list updates (via environment)
✅ Multi-language support (Hindi + English)
✅ Robust testing & validation

## Known Limitations

1. **3-word heuristic**: Phrases with >3 words are never classified as pure filler (prevents "um okay please wait" from being ignored)
2. **Confidence threshold**: Set to 0.6 by default; may need tuning for different environments
3. **Phrase fillers**: Multi-word fillers like "you know" require exact match

## Future Enhancements

- Dynamic runtime updates to filler list (currently requires restart)
- Machine learning-based filler detection
- Language auto-detection
- Configurable word-count heuristic threshold

## Files

- `agent3.py`: Main agent implementation with InterruptManager class
- `README.md`: This file
- `.env`: Configuration file (not tracked in git)
- `.env.template`: Template for environment configuration

## Made By

Mrinal Chaturvedi  
IIT Kanpur, Civil Engineering (3rd Year)  
SalesCode.ai Final Round Qualifier

## Development Process

I used Gemini AI to help with:
- Code structure and organization
- Documentation and docstrings  
- Error handling best practices

Core logic and algorithm design is my own:
- Context-aware filtering approach
- Mixed command extraction method
- Test scenario design
- Configuration strategy

All functionality validated through testing (33/33 scenarios pass).

## Time Spent

~12-15 hours (implementation, extended testing, edge case handling, documentation)

## Testing Instructions

1. **Run test harness**:
```bash
   python agent3.py test
```

2. **Verify output**:
   - All 33 tests should execute
   - Check for expected behavior labels: IGNORE, INTERRUPT, NORMAL, SKIP
   - Review logged confidence scores and timestamps

3. **Run live agent**:
```bash
   python agent3.py dev
```

4. **Manual testing**:
   - Say filler words while agent speaks (should be ignored)
   - Say commands while agent speaks (should interrupt)
   - Say fillers when agent quiet (should be processed)
