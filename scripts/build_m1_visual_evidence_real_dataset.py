from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_character_generator.application.services.visual_evidence_evaluation_service import (
    VisualEvidenceEvaluationDataset,
)
from novel_character_generator.domain.entities.document import TextChunk
from novel_character_generator.domain.policies.text_processing import (
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "tests/evaluation/m1_visual_evidence_real_v2.json"
CHUNK_TOKENS = 1_000


def owner(key: str, *accepted_mentions: str) -> dict[str, Any]:
    return {"key": key, "accepted_mentions": list(accepted_mentions)}


def candidate(
    key: str,
    quote: str,
    *,
    owner_policy: str,
    owner_key: str | None = None,
    alternatives: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "key": key,
        "owner_policy": owner_policy,
        "owner_key": owner_key,
        "evidence_quotes": [quote, *alternatives],
    }


def expected(
    *,
    owners: list[dict[str, Any]],
    required: list[dict[str, Any]],
    allowed: list[dict[str, Any]] | None = None,
    forbidden: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "owners": owners,
        "required_candidates": required,
        "allowed_candidates": allowed or [],
        "forbidden_candidates": forbidden or [],
        "allow_additional_candidates": True,
    }


CASE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "m1-v2-real-xiao-yan-xiao-mei-001",
        "category": "compound_age_face_and_owner",
        "purpose": "同一真实 Chunk 中分别保留萧炎脸貌与萧媚年龄、脸貌的完整关系。",
        "path": "tests/测试/斗破苍穹前四章.txt",
        "chunk_ordinal": 1,
        "expected": expected(
            owners=[
                owner("xiao_yan", "萧炎", "少年"),
                owner("xiao_mei", "萧媚", "少女"),
            ],
            required=[
                candidate(
                    "xiao_yan_young_face",
                    "少年缓缓抬起头来，露出一张有些清秀的稚嫩脸庞",
                    owner_policy="required",
                    owner_key="xiao_yan",
                ),
                candidate(
                    "xiao_mei_age_and_face",
                    "少女年龄不过十四左右，虽然并算不上绝色，不过那张稚气未脱的小脸，却是蕴含着淡淡的妩媚",
                    owner_policy="required",
                    owner_key="xiao_mei",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-xun-er-002",
        "category": "clothing_face_and_temperament",
        "purpose": "紫裙、稚嫩脸貌与年幼气质均应作为可逐字定位的视觉证据。",
        "path": "tests/测试/斗破苍穹前四章.txt",
        "chunk_ordinal": 2,
        "expected": expected(
            owners=[owner("xun_er", "萧薰儿", "少女", "紫裙少女")],
            required=[
                candidate(
                    "purple_dress_and_face",
                    "一位身着紫色衣裙的少女，正淡雅的站立，平静的稚嫩俏脸，并未因为众人的注目而改变分毫",
                    owner_policy="required",
                    owner_key="xun_er",
                ),
                candidate(
                    "young_transcendent_temperament",
                    "少女清冷淡然的气质，犹如清莲初绽，小小年纪，却已初具脱俗气质",
                    owner_policy="required",
                    owner_key="xun_er",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-tang-san-child-003",
        "category": "explicit_age_compound_appearance",
        "purpose": "儿童年龄、肤色、发型与衣着必须保留为语义完整的复合证据。",
        "path": "tests/测试/第2章 斗罗大陆，异界唐三（一）.txt",
        "chunk_ordinal": 0,
        "expected": expected(
            owners=[
                owner(
                    "tang_san",
                    "那是个只有五、六岁的孩子",
                    "孩子",
                    "男孩",
                    "男孩儿",
                    "他",
                )
            ],
            required=[
                candidate(
                    "child_age_skin_hair_clothes",
                    "那是个只有五、六岁的孩子，显然，他经常承受太阳的温暖，皮肤呈现出健康的小麦色，黑色短发看上去很利落，一身衣服虽然朴素，到也干净",
                    owner_policy="required",
                    owner_key="tang_san",
                )
            ],
            allowed=[
                candidate(
                    "temporary_purple_eyes",
                    "他眼眸中竟然闪烁着一层淡淡的紫意",
                    owner_policy="allowed",
                    owner_key="tang_san",
                )
            ],
        ),
    },
    {
        "id": "m1-v2-real-tang-hao-dense-004",
        "category": "inferred_age_dense_appearance",
        "purpose": "唐昊的近似年龄、体格、衣着、肤色、脸貌、头发和胡须关系不得被截断。",
        "path": "tests/测试/第2章 斗罗大陆，异界唐三（一）.txt",
        "chunk_ordinal": 3,
        "expected": expected(
            owners=[owner("tang_hao", "中年男子", "那是一名中年男子", "唐昊")],
            required=[
                candidate(
                    "approximate_age_and_build",
                    "那是一名中年男子，看上去大约有接近五十岁的样子，但身材却非常高大魁梧",
                    owner_policy="required",
                    owner_key="tang_hao",
                ),
                candidate(
                    "clothes_skin_face_hair_beard",
                    "破损的袍子穿在身上，上面甚至连补丁都没有，露出下面古铜色的皮肤，原本还算端正的五官却蒙着一层蜡黄色，一副睡眼朦胧的样子，头发乱糟糟的像鸟窝一般，一脸的胡子已经不知道有多少日子没有整理过了",
                    owner_policy="required",
                    owner_key="tang_hao",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-presentation-and-elder-005",
        "category": "presentation_and_local_owner",
        "purpose": (
            "真实长 Chunk 中同时覆盖换衣 presentation、少年脸貌，并区分"
            "青衫管家与月白衣袍客人的局部 owner。"
        ),
        "path": "tests/测试/斗破苍穹前四章.txt",
        "chunk_ordinal": 9,
        "expected": expected(
            owners=[
                owner("xiao_yan", "萧炎", "少年"),
                owner(
                    "qing_robed_steward",
                    "一名青衫老者",
                    "青衫老者",
                    "墨管家",
                    "老管家",
                ),
                owner(
                    "moon_white_elder",
                    "一位身穿月白衣袍的老者",
                    "老者",
                    "老人",
                    "这老人",
                ),
            ],
            required=[
                candidate(
                    "changed_clothes",
                    "换了一身衣衫",
                    owner_policy="required",
                    owner_key="xiao_yan",
                ),
                candidate(
                    "young_face",
                    "少年稚嫩的脸庞",
                    owner_policy="required",
                    owner_key="xiao_yan",
                ),
                candidate(
                    "qing_robed_steward_clothing",
                    "一名青衫老者",
                    owner_policy="required",
                    owner_key="qing_robed_steward",
                ),
                candidate(
                    "moon_white_elder_visual_profile",
                    "一位身穿月白衣袍的老者，老者满脸笑容，神采奕奕，一双有些细小的双眼，却是精光偶闪",
                    owner_policy="required",
                    owner_key="moon_white_elder",
                    alternatives=(
                        "身穿月白衣袍的老者，老者满脸笑容，神采奕奕，一双有些细小的双眼，却是精光偶闪",
                    ),
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-multi-owner-age-006",
        "category": "multi_owner_age_and_accessory",
        "purpose": "相邻男女的年龄、体貌和佩戴物必须分别绑定到正确局部 owner。",
        "path": "tests/测试/斗破苍穹前四章.txt",
        "chunk_ordinal": 10,
        "expected": expected(
            owners=[owner("young_man", "男子", "青年"), owner("young_woman", "少女")],
            required=[
                candidate(
                    "man_age_face_build",
                    "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
                    owner_policy="required",
                    owner_key="young_man",
                ),
                candidate(
                    "woman_relative_age",
                    "这位少女年龄和萧炎相仿",
                    owner_policy="required",
                    owner_key="young_woman",
                ),
                candidate(
                    "woman_jade_pendant",
                    "少女娇嫩的耳垂上吊有着绿色的玉坠",
                    owner_policy="required",
                    owner_key="young_woman",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-inferred-age-007",
        "category": "inferred_age_relation",
        "purpose": "唐昊的苍老比较和爷爷类比必须保留为完整推断关系。",
        "path": "tests/测试/第2章 斗罗大陆，异界唐三（一）.txt",
        "chunk_ordinal": 4,
        "expected": expected(
            owners=[owner("tang_hao", "唐昊", "父亲")],
            required=[
                candidate(
                    "older_than_peers_inference",
                    "可唐昊看起来却要比他们苍老的多，反倒像是唐三的爷爷一般",
                    owner_policy="required",
                    owner_key="tang_hao",
                    alternatives=(
                        "唐昊看起来却要比他们苍老的多，反倒像是唐三的爷爷一般",
                    ),
                ),
                candidate(
                    "sallow_face",
                    "暗黄的脸色这才看上去多了几分光泽",
                    owner_policy="required",
                    owner_key="tang_hao",
                    alternatives=("暗黄的脸色",),
                ),
            ],
            allowed=[
                candidate(
                    "drooping_eyelids",
                    "耷拉的眼皮睁开了几分",
                    owner_policy="allowed",
                    owner_key="tang_hao",
                )
            ],
        ),
    },
    {
        "id": "m1-v2-real-relative-age-accessory-008",
        "category": "relative_age_hair_accessory",
        "purpose": "相对年龄、明确年龄、辫子、脚环和虎牙在真实长 Chunk 中均可唯一定位。",
        "path": "tests/测试/牧神纪前20章.txt",
        "chunk_ordinal": 54,
        "expected": expected(
            owners=[
                owner("qin_mu", "秦牧"),
                owner("xian_qinger", "小女孩儿", "女孩儿", "那女孩儿", "仙清儿"),
            ],
            required=[
                candidate(
                    "removed_iron_shoes",
                    "秦牧坐在石阶上，脱掉脚上的铁鞋，解开缚在小腿上的铁锭",
                    owner_policy="required",
                    owner_key="qin_mu",
                ),
                candidate(
                    "girl_age_and_braids",
                    "一个小女孩儿，年纪与他仿佛，也是十一二岁，梳着三根小辫，两根较细的辫子垂在胸前，粗的辫子垂在身后",
                    owner_policy="required",
                    owner_key="xian_qinger",
                    alternatives=(
                        "小女孩儿，年纪与他仿佛，也是十一二岁，梳着三根小辫，"
                        "两根较细的辫子垂在胸前，粗的辫子垂在身后",
                    ),
                ),
                candidate(
                    "ankle_ring",
                    "那女孩儿脚丫晃啊晃，脚踝处的金环碰来碰去",
                    owner_policy="required",
                    owner_key="xian_qinger",
                ),
                candidate(
                    "tiger_teeth",
                    "露出两只小虎牙",
                    owner_policy="required",
                    owner_key="xian_qinger",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-transformation-009",
        "category": "dense_transformation",
        "purpose": "多句身体变化须保留变化关系；代词 owner 可绑定，也允许保守留空。",
        "path": "tests/测试/牧神纪前20章.txt",
        "chunk_ordinal": 55,
        "expected": expected(
            owners=[owner("xian_qinger", "仙清儿", "小女孩仙清儿", "她", "怪物", "它")],
            required=[
                candidate(
                    "lower_body_transformation",
                    "仙清儿脸色陡变，霎时间变得无比狰狞丑陋，这个小女孩的身体膨胀起来，下身发出嗤嗤嗤的声响，一条条骨节嶙峋的腿刺破她的裙子，铮铮扎在地面上，身体变得又粗又长，像是一只由骨头组成的大蜈蚣",
                    owner_policy="allowed",
                    owner_key="xian_qinger",
                ),
                candidate(
                    "upper_body_transformation",
                    "她的上身背后则有骨甲高高隆起，让她的身子佝偻起来，一条条骨骼组成的手臂张开，指骨利爪，锋利无比",
                    owner_policy="allowed",
                    owner_key="xian_qinger",
                ),
                candidate(
                    "head_and_face_transformation",
                    "她的脑后也有长出一根根鹿角般弯曲的骨刺，脸上丘壑纵横，说不出的可怕",
                    owner_policy="allowed",
                    owner_key="xian_qinger",
                ),
                candidate(
                    "returns_to_girl_form",
                    "它又变成小女孩仙清儿的模样，衣衫半解",
                    owner_policy="allowed",
                    owner_key="xian_qinger",
                ),
            ],
        ),
    },
    {
        "id": "m1-v2-real-classic-apparel-010",
        "category": "classic_apparel_with_adjacent_held_items",
        "purpose": "古典服饰整体应保留；同一连续引文附带兵器或坐骑不因此判错。",
        "path": "tests/测试/水浒传前两章.txt",
        "chunk_ordinal": 19,
        "expected": expected(
            owners=[owner("shi_jin", "史进"), owner("chen_da", "陈达")],
            required=[
                candidate(
                    "shi_jin_apparel",
                    "史进头戴一字巾，身披朱红甲，上穿青锦袄，下着抹绿靴，腰系皮搭膊，前后铁掩心",
                    owner_policy="required",
                    owner_key="shi_jin",
                ),
                candidate(
                    "chen_da_apparel",
                    "陈达头戴干红凹面巾，身披裹金生铁甲，上穿一领红衲袄，脚穿一对吊墩靴，腰系七尺攒线搭膊",
                    owner_policy="required",
                    owner_key="chen_da",
                ),
            ],
        ),
    },
)


def source_chunks() -> dict[tuple[str, int], TextChunk]:
    selected: dict[tuple[str, int], TextChunk] = {}
    ordinals_by_path: dict[str, set[int]] = {}
    for spec in CASE_SPECS:
        ordinals_by_path.setdefault(spec["path"], set()).add(spec["chunk_ordinal"])
    for relative_path, ordinals in ordinals_by_path.items():
        source_path = PROJECT_ROOT / relative_path
        raw_text, _encoding = decode_text(source_path.read_bytes())
        normalized = normalize_text(raw_text)
        chunks = build_chunks(
            normalized,
            detect_chapters(normalized.text),
            target_tokens=CHUNK_TOKENS,
        )
        for ordinal in ordinals:
            selected[(relative_path, ordinal)] = chunks[ordinal]
    return selected


def build_dataset() -> VisualEvidenceEvaluationDataset:
    chunks = source_chunks()
    cases: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        chunk = chunks[(spec["path"], spec["chunk_ordinal"])]
        cases.append(
            {
                "id": spec["id"],
                "category": spec["category"],
                "purpose": spec["purpose"],
                "source_chunk": {
                    "path": spec["path"],
                    "chunk_tokens": CHUNK_TOKENS,
                    "chunk_ordinal": chunk.ordinal,
                    "chapter_ordinal": chunk.chapter_ordinal,
                    "text_sha256": chunk.content_hash,
                },
                "input": {
                    "schema_version": "visual-evidence-discovery-input-v2",
                    "chunk_id": spec["id"],
                    "chunk_text": chunk.content,
                    "previous_tail": None,
                },
                "expected": spec["expected"],
            }
        )
    return VisualEvidenceEvaluationDataset.model_validate(
        {
            "schema_version": "visual-evidence-evaluation-dataset-v2.4",
            "dataset_version": "m1-visual-evidence-real-v2.5-draft",
            "node_contract_version": "visual-evidence-contract-v2",
            "prompt_version": "visual-evidence-discovery-prompt-v2.8",
            "review_status": "draft_user_review_required",
            "review_notes": [
                "10 个输入均由生产 text_processing.build_chunks(target_tokens=1000) "
                "从 tests/测试 原文逐章切分，并记录可复验的原文件、chunk ordinal、"
                "chapter ordinal 与 SHA-256。",
                "其中 6 个复用既有真实评测 chunk，新增 4 个 chunk；"
                "总计覆盖 tests/测试 下四份原文。",
                "gold quote 采用最小但语义完整、且适合 N2 唯一定位的连续逐字原文；"
                "年龄、推断、presentation 与 transformation 关系不得被裁掉。",
                "真实长 Chunk 仅标注本轮审核切片，allow_additional_candidates=true；"
                "未标注的合理候选进入 review，不直接判错。",
                "owner_policy 分为 required、allowed、must_be_null；"
                "本真实集覆盖 required/allowed，must_be_null 由短边界集覆盖。",
                "第 3 章样例将青衫管家与月白衣袍客人标为不同 owner；"
                "模型用于月白衣袍候选的‘老者/老人’作为候选局部 alias 接受，"
                "不得据此建立跨段全局身份。",
                "v2.4-draft 根据 v2.3 首次真实运行补全 001/002/003 的明确人名或"
                "完整人物短语 owner alias，并为 007 增加逐字且唯一定位的可接受跨度。",
                "v2.5-draft 补全 003/004/008/009 经审计确认的局部 owner alias，"
                "并为 008 增加语义完整且可唯一定位的年龄与发辫跨度备选。",
                "本草案只复用 Prompt v2.6 的既有 outputs 做离线重评分，不触发新的 Provider 调用。",
                "主 Prompt 已按用户决定回退到 v2.8；v2.9 运行工件只保留为历史证据，"
                "金标、Dataset 版本、Rubric 与 Source Match Policy 不变。",
                "本轮人工审查允许一条逐字且唯一的连续候选覆盖相邻多个金标；"
                "010 暂不因服饰引文同时包含兵器或坐骑而判失败。",
                "不同 owner 不得共享标准化 accepted mention；本版本修改了已批准金标，"
                "必须重新人工审核后才能运行新的 Provider Gate。",
            ],
            "cases": cases,
        }
    )


def main() -> None:
    dataset = build_dataset()
    OUTPUT_PATH.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)} ({len(dataset.cases)} cases)")


if __name__ == "__main__":
    main()
