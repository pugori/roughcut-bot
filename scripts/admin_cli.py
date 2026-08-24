"""Admin CLI Tool for Passcode Issuance and Streamer Watchlist Management."""

import argparse
import sys
from pathlib import Path

from bot.discord_bot import generate_secure_passcode
from channel_dna.core.chzzk_client import extract_chzzk_channel_id
from channel_dna.core.db import DBManager


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="ChannelDNA Admin Passcode & Watchlist CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: issue
    p_issue = subparsers.add_parser("issue", help="Issue a single-use passcode for a streamer")
    p_issue.add_argument("--streamer", required=True, help="Streamer Name (e.g. 양망두)")
    p_issue.add_argument("--channel", required=True, help="Chzzk Channel URL or 32-char ID")
    p_issue.add_argument("--dna", default="", help="Target DNA Profile Style Name (optional)")

    # Command: list
    subparsers.add_parser("list", help="List all registered streamer bindings and statuses")

    # Command: test_bind
    p_bind = subparsers.add_parser("test_bind", help="Test binding a passcode with a mock Discord ID")
    p_bind.add_argument("--passcode", required=True, help="Passcode to verify")
    p_bind.add_argument("--user-id", type=int, required=True, help="Mock Discord User ID")

    # Command: unbind
    p_unbind = subparsers.add_parser("unbind", help="Remove a streamer from monitoring")
    p_unbind.add_argument("--streamer", required=True, help="Streamer Name or Channel ID")

    args = parser.parse_args()
    db = DBManager()

    if args.command == "issue":
        ch_id = extract_chzzk_channel_id(args.channel)
        if not ch_id or len(ch_id) < 10:
            print(f"❌ Invalid Chzzk Channel ID: {args.channel}")
            sys.exit(1)

        passcode = generate_secure_passcode(args.streamer)
        dna_prof = args.dna.strip() if args.dna else args.streamer.strip()
        db.create_passcode_binding(ch_id, args.streamer, passcode, target_dna_profile=dna_prof)
        print("======================================================================")
        print(f"✓ 1회용 등록 암호 발급 완료")
        print("======================================================================")
        print(f"• 스트리머: {args.streamer}")
        print(f"• 적용 DNA: {dna_prof} 스타일")
        print(f"• 채널 ID : {ch_id}")
        print(f"• 인증암호: {passcode}")
        print("----------------------------------------------------------------------")
        print("[스트리머 전달용 안내 문구]")
        print(f"안녕하세요. 치지직 방송 종료 시 가편집 타임라인과 자막을 자동 전송하는 봇입니다.\n")
        print(f"1. 봇 초대 링크를 통해 1:1 대화방을 엽니다.")
        print(f"2. 대화창에 아래 명령어를 입력하여 등록을 완료해 주세요.")
        print(f"👉 /인증 암호:{passcode}")
        print("======================================================================")

    elif args.command == "list":
        bindings = db.get_all_streamer_bindings()
        print("======================================================================")
        print(f"📋 스트리머 모니터링 현황 (총 {len(bindings)}개)")
        print("======================================================================")
        if not bindings:
            print("등록된 스트리머 채널이 없습니다.")
        for b in bindings:
            st = b.get("streamer_name")
            ch = b.get("channel_id")
            bound = "✓ 인증완료" if b.get("is_bound") else "⏳ 대기중"
            d_id = b.get("master_discord_id") or "미지정"
            code = b.get("passcode") or "폐기완료"
            vod = b.get("last_processed_video_no") or "없음"
            print(f"[{bound}] {st} | 채널: {ch} | 디스코드ID: {d_id} | 암호: {code} | 최근VOD: {vod}")
        print("======================================================================")

    elif args.command == "test_bind":
        res = db.verify_and_bind_passcode(args.passcode, args.user_id)
        if res:
            print("======================================================================")
            print(f"✓ [인증 성공] 채널: {res['streamer_name']} ({res['channel_id']})")
            print(f"• 수신자 디스코드 ID: {res['master_discord_id']}")
            print("• 1회용 암호가 폐기되었으며 독점 바인딩되었습니다.")
            print("======================================================================")
        else:
            print("❌ 인증 실패: 유효하지 않거나 이미 사용된 암호입니다.")

    elif args.command == "unbind":
        res = db.unbind_streamer(args.streamer)
        if res:
            print(f"✓ [{args.streamer}] 모니터링 및 바인딩이 해지되었습니다.")
        else:
            print(f"❌ [{args.streamer}] 대상을 찾을 수 없습니다.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
