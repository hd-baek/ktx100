설치:
pip install flask pyte pexpect

배치:
mkdir -p ~/ktx100_termux_remote
(이 ZIP의 파일들을 그 폴더에 넣기)

실행:
chmod +x ~/ktx100_termux_remote/*.sh
~/ktx100_termux_remote/start_dual.sh

확인:
ss -ltn | grep -E ':8765|:8766'

Access Key:
~/ktx100_termux_remote/show_access_keys.sh

접속:
http://폰의-Tailscale-IP:8765
http://폰의-Tailscale-IP:8766
