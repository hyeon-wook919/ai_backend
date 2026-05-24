import pandas as pd
import os

# 엑셀 파일 이름 (사진에 있는 파일명과 정확히 일치시킴)
excel_file = "정책_리스트.xlsx"

output_lines = ["REAL_DB_POLICIES = ["]
policy_id = 1

print(f"⏳ '{excel_file}' 파일을 읽는 중입니다...")

try:
    # sheet_name=None으로 설정하면 엑셀 안의 모든 시트를 한 번에 다 가져옵니다.
    df_dict = pd.read_excel(excel_file, sheet_name=None)
    
    for sheet_name, df in df_dict.items():
        print(f" - '{sheet_name}' 카테고리 변환 중...")
        df = df.fillna("") # 빈 칸 처리
        
        for _, row in df.iterrows():
            policy_name = str(row.get("정책명", "")).strip()
            # 정책명이 비어있는 빈 줄은 건너뜁니다.
            if not policy_name:
                continue
                
            ai_text = str(row.get("ai_search_text", "")).strip()
            agency = str(row.get("기관", "")).strip()
            summary = str(row.get("요약", "")).strip()
            
            # 파이썬 딕셔너리 문자열 만들기
            dict_str = f"""    {{
        "policy_id": {policy_id},
        "policy_name": "{policy_name}",
        "category": "{sheet_name}",
        "agency": "{agency}",
        "summary": "{summary}",
        "content": "{ai_text}",
        "ai_search_text": "{ai_text}"
    }},"""
            output_lines.append(dict_str)
            policy_id += 1

    output_lines.append("]")

    # 결과를 텍스트 파일로 저장
    with open("output_code.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ 성공! 총 {policy_id - 1}개의 정책이 output_code.txt 파일로 생성되었습니다!")

except Exception as e:
    print(f"❌ 에러 발생: {e}\n엑셀 파일이 열려있다면 닫고 다시 실행해주세요.")