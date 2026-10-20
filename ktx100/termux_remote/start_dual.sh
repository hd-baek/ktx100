#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
mkdir -p "$HOME/.ktx100-remote-a" "$HOME/.ktx100-remote-b"
nohup python "$HOME/ktx100_termux_remote/ktx100_remote_A.py" > "$HOME/.ktx100-remote-a/nohup.log" 2>&1 &
sleep 1
nohup python "$HOME/ktx100_termux_remote/ktx100_remote_B.py" > "$HOME/.ktx100-remote-b/nohup.log" 2>&1 &
echo "A/B 서버 시작 완료"
