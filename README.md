# KTX100

KTX 전용 커스텀 예매 CLI입니다.

## 특징
- KTX 전용 동작
- 별도의 열차 운영사 선택 단계 없이 바로 KTX로 진행
- 현재 커스텀 KTX 로그인/조회 백엔드 포함
- 실행 명령어: `ktx100`

## Termux 설치

```bash
pkg update
pkg install python git -y

git clone https://github.com/hd-baek/ktx100.git
cd ktx100
pip install .
ktx100
```

## 업데이트

```bash
cd ~/ktx100
git pull
pip install . --upgrade
```

## 디버그 실행

```bash
ktx100 --debug
```
