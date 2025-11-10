# webmon - Automatic Monitor for Web Status
This Program is a Python-based monitoring tool that checks multiple websites in parallel and automatically sends Telegram alerts when response delays or connection failures are detected.

Features
 - Multi-threaded parallel scanning (based on ThreadPoolExecutor)
 - Ignores SSL certificate errors and handles exceptions automatically
 - Detects and warns about slow responses
 - Integrated Telegram alerts (bot_token, chat_id based)
 - Per-site configuration via individual .txt files
 - Automatic suppression of SSL-related error messages (e.g., CERTIFICATE_VERIFY_FAILED)
 - Session recreation for long-term stability

🔧 Pre-Configuration
Create a .txt file for each website you want to monitor.
The filename can be anything you like.

```
Example: target_sites/site.txt

url = https://www.mysite.com
timeout = 10
slow_threshold = 3
note = My personal website
```
Key	Description
url	: Target site URL
timeout :	Request timeout (seconds)
slow_threshold	: Threshold for slow response warnings (seconds)
note	: A short note shown in Telegram alerts

```
⚙️ [setting.ini] (Configuration File)

[General]
concurrent_limit = 5     ; Number of sites to check simultaneously
interval = 2             ; Delay (seconds) between each batch
cooldown = 5             ; Wait time (seconds) after full cycle

[Telegram]
bot_token = 123456789:ABCDEF1234567890abcdef
chat_id = 987654321
```

```
▶️ How to Run
python3 website_monitor.py
```
```
📂 Directory Structure
webmon/
├── website_monitor.py      # Main program file
├── setting.ini             # Configuration (auto-generated on first run)
└── target_sites/           # Folder containing individual site configs
    ├── site1.txt
    ├── site2.txt
    └── ...
```
```
🚧 In Development

 - Option to toggle SSL verification ON/OFF
 - Additional alert APIs (KakaoTalk, Email, etc.)
 - Defacing detection feature
```
