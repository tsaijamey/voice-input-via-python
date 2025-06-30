# 应用程序架构

本文档概述了应用程序的架构，为清晰起见，分为多个图表。

## 1. 高层组件架构

此图显示了主要组件以及它们与两个主要用户触发流程的关系。

```mermaid
graph TD
    subgraph "Core Infrastructure"
        ConfigLoader["core/config_loader.py"]
        HotkeyManager["core/hotkey_manager.py"]
        InputAutomationService["services/input_automation_service.py"]
    end

    subgraph "Main Application Logic"
        Main["main.py (Orchestrator)"]
    end

    subgraph "Business Flows"
        Flow1["Flow 1: Voice-to-Text with Vision"]
        Flow2["Flow 2: Selected Text Processing"]
    end

    Main -- "Loads config from" --> ConfigLoader
    Main -- "Initializes & Starts" --> HotkeyManager
    HotkeyManager -- "Triggers" --> Flow1
    HotkeyManager -- "Triggers" --> Flow2
    Flow1 -- "Uses" --> InputAutomationService
    Flow2 -- "Uses" --> InputAutomationService
```

## 2. 流程 1：带视觉的语音转文本

此流程由全局热键触发以开始/停止录音。它捕获音频和屏幕上下文，转录音频，通过视觉分析增强文本，并输出结果。

```mermaid
graph TD
    User_F1["User Presses Toggle Key"] --> HotkeyManager["core/hotkey_manager.py"]
    HotkeyManager -- "Triggers callback in" --> Main["main.py"]
    
    Main -- "Controls UI" --> TimerOverlay["services/timer_overlay.py (ControlWidget)"]
    TimerOverlay -- "Sends User Actions (start/stop)" --> Main
    
    Main -- "Starts/Stops" --> RecordingService["services/recording_service.py"]
    RecordingService -- "Audio Chunks" --> Main
    
    Main -- "Starts" --> VisionService["services/vision_service.py"]
    VisionService -- "Analyzes screenshot via" --> GoogleAPI["Google GenAI API"]
    VisionService -- "Screen Context" --> ContentEnhancementService
    
    Main -- "Transcribes via" --> ASRService["services/asr_service.py"]
    ASRService -- "Transcribes audio via" --> GroqAPI["Groq API"]
    ASRService -- "Live/Corrected Transcript" --> Main
    Main -- "Updates UI with" --> TimerOverlay

    Main -- "Enhances final text via" --> ContentEnhancementService["services/content_enhancement_service.py"]
    ASRService -- "Corrected Transcript" --> ContentEnhancementService
    ContentEnhancementService -- "Enhances text via" --> GoogleAPI
    
    ContentEnhancementService -- "Enhanced Text" --> Main
    Main -- "Pastes result via" --> InputAutomationService["services/input_automation_service.py"]
    Main -- "Saves log via" --> OutputHandler["output_handler.py"]
```

## 3. 流程 2：选定文本处理

此流程在选定文本时由不同的热键触发。它复制文本，翻译或增强其样式，然后将结果粘贴回去。

```mermaid
graph TD
    User_F2["User Selects Text & Presses Key"] --> HotkeyManager["core/hotkey_manager.py"]
    HotkeyManager -- "Triggers" --> TextProcessingService["services/text_processing_service.py"]
    
    Main["main.py"] -- "Initializes" --> TextProcessingService
    
    TextProcessingService -- "Copies text via" --> InputAutomationService["services/input_automation_service.py"]
    TextProcessingService -- "Controls UI" --> TextProcessingOverlay["services/text_processing_overlay.py"]
    TextProcessingOverlay -- "Sends User Actions (style selection)" --> TextProcessingService
    
    TextProcessingService -- "Translates/Enhances via" --> TranslationService["services/translation_service.py"]
    TranslationService -- "Processes text via" --> GoogleAPI["Google GenAI API"]
    TranslationService -- "Result" --> TextProcessingService
    
    TextProcessingService -- "Pastes result via" --> InputAutomationService
```