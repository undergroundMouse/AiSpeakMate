"""Seed data for initial app setup - English learning scenes."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.scene import Scene, SceneCategory, SceneSentencePattern, SceneVocabulary

SEED_CATEGORIES = [
    {
        "name": "Daily Life",
        "icon_url": "/icons/daily-life.svg",
        "sort_order": 1,
        "scenes": [
            {
                "name": "Ordering Coffee",
                "description": "Practice ordering drinks and snacks at a café",
                "thumbnail_url": "/images/scenes/coffee.jpg",
                "role_prompt": "You are a friendly barista at a busy coffee shop. Help the customer order their drink, ask about size and customizations, and make small talk about the weather.",
                "opening_line": "Good morning! Welcome to Brew & Bean. What can I get for you today?",
                "difficulty_levels": ["beginner", "intermediate"],
                "tags": ["food", "café", "ordering"],
                "suggested_duration": 300,
                "vocabulary": [
                    {"word": "latte", "phonetic": "/ˈlɑːteɪ/", "translation": "拿铁", "part_of_speech": "noun"},
                    {"word": "espresso", "phonetic": "/eˈspresəʊ/", "translation": "浓缩咖啡", "part_of_speech": "noun"},
                    {"word": "cappuccino", "phonetic": "/ˌkæpuˈtʃiːnəʊ/", "translation": "卡布奇诺", "part_of_speech": "noun"},
                    {"word": "skim milk", "phonetic": "/skɪm mɪlk/", "translation": "脱脂牛奶", "part_of_speech": "noun phrase"},
                    {"word": "takeaway", "phonetic": "/ˈteɪkəweɪ/", "translation": "外卖", "part_of_speech": "noun/adjective"},
                ],
                "sentence_patterns": [
                    {"pattern": "I'd like a ... please.", "translation": "我想要一杯...", "example": "I'd like a medium latte please."},
                    {"pattern": "Can I have ... with ...?", "translation": "我可以要...加...吗？", "example": "Can I have a cappuccino with skim milk?"},
                ],
            },
            {
                "name": "At the Restaurant",
                "description": "Learn how to order food, ask about the menu, and interact with waitstaff",
                "thumbnail_url": "/images/scenes/restaurant.jpg",
                "role_prompt": "You are a professional waiter at an upscale restaurant. Help the customer with menu recommendations, take their order, and check on their satisfaction.",
                "opening_line": "Good evening! Welcome to The Garden Bistro. Do you have a reservation?",
                "difficulty_levels": ["beginner", "intermediate", "advanced"],
                "tags": ["food", "dining", "restaurant"],
                "suggested_duration": 420,
                "vocabulary": [
                    {"word": "appetizer", "phonetic": "/ˈæpɪtaɪzər/", "translation": "开胃菜", "part_of_speech": "noun"},
                    {"word": "main course", "phonetic": "/meɪn kɔːrs/", "translation": "主菜", "part_of_speech": "noun phrase"},
                    {"word": "medium rare", "phonetic": "/ˈmiːdiəm reər/", "translation": "五分熟", "part_of_speech": "adjective"},
                    {"word": "check", "phonetic": "/tʃek/", "translation": "账单", "part_of_speech": "noun"},
                    {"word": "reservation", "phonetic": "/ˌrezərˈveɪʃən/", "translation": "预订", "part_of_speech": "noun"},
                ],
                "sentence_patterns": [
                    {"pattern": "I'll have the ..., please.", "translation": "我要...，谢谢。", "example": "I'll have the grilled salmon, please."},
                    {"pattern": "Could you recommend ...?", "translation": "你能推荐...吗？", "example": "Could you recommend a good red wine?"},
                ],
            },
            {
                "name": "Shopping for Clothes",
                "description": "Practice asking about sizes, colors, prices, and trying on clothes",
                "thumbnail_url": "/images/scenes/shopping.jpg",
                "role_prompt": "You are a helpful sales assistant in a clothing store. Help the customer find the right size, suggest styles, and handle returns or exchanges.",
                "opening_line": "Hi there! Can I help you find anything in particular today? We have a sale on summer items!",
                "difficulty_levels": ["beginner", "intermediate"],
                "tags": ["shopping", "clothes", "fashion"],
                "suggested_duration": 360,
                "vocabulary": [
                    {"word": "fitting room", "phonetic": "/ˈfɪtɪŋ ruːm/", "translation": "试衣间", "part_of_speech": "noun phrase"},
                    {"word": "size", "phonetic": "/saɪz/", "translation": "尺码", "part_of_speech": "noun"},
                    {"word": "on sale", "phonetic": "/ɒn seɪl/", "translation": "打折", "part_of_speech": "phrase"},
                    {"word": "receipt", "phonetic": "/rɪˈsiːt/", "translation": "收据", "part_of_speech": "noun"},
                    {"word": "exchange", "phonetic": "/ɪksˈtʃeɪndʒ/", "translation": "换货", "part_of_speech": "noun/verb"},
                ],
                "sentence_patterns": [
                    {"pattern": "Do you have this in ...?", "translation": "这件有...吗？", "example": "Do you have this in a medium?"},
                    {"pattern": "Can I try this on?", "translation": "我可以试穿吗？", "example": "Can I try this on?"},
                ],
            },
        ],
    },
    {
        "name": "Travel & Transport",
        "icon_url": "/icons/travel.svg",
        "sort_order": 2,
        "scenes": [
            {
                "name": "Airport Check-in",
                "description": "Practice checking in for a flight, dealing with luggage, and boarding",
                "thumbnail_url": "/images/scenes/airport.jpg",
                "role_prompt": "You are an airline check-in agent at the airport. Help the passenger check in, weigh their luggage, assign seats, and provide boarding information.",
                "opening_line": "Good afternoon! Welcome to SkyLine Airways. May I see your passport and booking confirmation, please?",
                "difficulty_levels": ["intermediate", "advanced"],
                "tags": ["travel", "airport", "flight"],
                "suggested_duration": 360,
                "vocabulary": [
                    {"word": "boarding pass", "phonetic": "/ˈbɔːrdɪŋ pæs/", "translation": "登机牌", "part_of_speech": "noun phrase"},
                    {"word": "carry-on", "phonetic": "/ˈkæri ɒn/", "translation": "随身行李", "part_of_speech": "noun"},
                    {"word": "check-in", "phonetic": "/tʃek ɪn/", "translation": "办理登机", "part_of_speech": "noun/verb"},
                    {"word": "departure gate", "phonetic": "/dɪˈpɑːrtʃər ɡeɪt/", "translation": "登机口", "part_of_speech": "noun phrase"},
                    {"word": "layover", "phonetic": "/ˈleɪəʊvər/", "translation": "中转停留", "part_of_speech": "noun"},
                ],
                "sentence_patterns": [
                    {"pattern": "I'd like to check in for my flight to ...", "translation": "我想办理去...的登机手续", "example": "I'd like to check in for my flight to London."},
                    {"pattern": "Is my luggage within the weight limit?", "translation": "我的行李在重量限制内吗？", "example": "Is my luggage within the weight limit?"},
                ],
            },
            {
                "name": "Hotel Check-in",
                "description": "Practice booking a room, checking in, and requesting hotel services",
                "thumbnail_url": "/images/scenes/hotel.jpg",
                "role_prompt": "You are a receptionist at a hotel. Welcome the guest, confirm their reservation, explain hotel amenities, and handle any special requests.",
                "opening_line": "Good evening! Welcome to Grand Horizon Hotel. Do you have a reservation with us tonight?",
                "difficulty_levels": ["beginner", "intermediate"],
                "tags": ["travel", "hotel", "accommodation"],
                "suggested_duration": 300,
                "vocabulary": [
                    {"word": "check-out", "phonetic": "/tʃek aʊt/", "translation": "退房", "part_of_speech": "noun/verb"},
                    {"word": "amenities", "phonetic": "/əˈmenətiz/", "translation": "设施", "part_of_speech": "noun"},
                    {"word": "room service", "phonetic": "/ruːm ˈsɜːrvɪs/", "translation": "客房服务", "part_of_speech": "noun phrase"},
                    {"word": "king-size bed", "phonetic": "/kɪŋ saɪz bed/", "translation": "特大床", "part_of_speech": "noun phrase"},
                    {"word": "wake-up call", "phonetic": "/weɪk ʌp kɔːl/", "translation": "叫醒服务", "part_of_speech": "noun phrase"},
                ],
                "sentence_patterns": [
                    {"pattern": "I have a reservation under the name ...", "translation": "我以...的名字预订了", "example": "I have a reservation under the name Smith."},
                    {"pattern": "What time is check-out?", "translation": "退房时间是几点？", "example": "What time is check-out?"},
                ],
            },
            {
                "name": "Asking for Directions",
                "description": "Practice asking for and giving directions on the street",
                "thumbnail_url": "/images/scenes/directions.jpg",
                "role_prompt": "You are a friendly local on the street. Help the tourist find their way, give clear directions with landmarks, and suggest nearby attractions.",
                "opening_line": "Hi! You look a bit lost. Can I help you find something?",
                "difficulty_levels": ["beginner", "intermediate", "advanced"],
                "tags": ["travel", "directions", "navigation"],
                "suggested_duration": 240,
                "vocabulary": [
                    {"word": "intersection", "phonetic": "/ˌɪntərˈsekʃən/", "translation": "十字路口", "part_of_speech": "noun"},
                    {"word": "straight ahead", "phonetic": "/streɪt əˈhed/", "translation": "一直往前", "part_of_speech": "adverb phrase"},
                    {"word": "block", "phonetic": "/blɒk/", "translation": "街区", "part_of_speech": "noun"},
                    {"word": "landmark", "phonetic": "/ˈlændmɑːrk/", "translation": "地标", "part_of_speech": "noun"},
                    {"word": "roundabout", "phonetic": "/ˈraʊndəbaʊt/", "translation": "环岛", "part_of_speech": "noun"},
                ],
                "sentence_patterns": [
                    {"pattern": "How do I get to ...?", "translation": "去...怎么走？", "example": "How do I get to the train station?"},
                    {"pattern": "Go straight for ... blocks, then turn ...", "translation": "直走...个街区，然后...转", "example": "Go straight for two blocks, then turn left at the traffic light."},
                ],
            },
        ],
    },
    {
        "name": "Business & Work",
        "icon_url": "/icons/business.svg",
        "sort_order": 3,
        "scenes": [
            {
                "name": "Job Interview",
                "description": "Practice answering common interview questions and introducing yourself professionally",
                "thumbnail_url": "/images/scenes/interview.jpg",
                "role_prompt": "You are an HR manager conducting a job interview for a software engineer position. Ask about the candidate's experience, strengths, weaknesses, and career goals. Maintain a professional but friendly tone.",
                "opening_line": "Good morning! Thank you for coming in today. Why don't we start with you telling me a bit about yourself?",
                "difficulty_levels": ["intermediate", "advanced"],
                "tags": ["business", "interview", "career"],
                "suggested_duration": 600,
                "vocabulary": [
                    {"word": "qualification", "phonetic": "/ˌkwɒlɪfɪˈkeɪʃən/", "translation": "资历", "part_of_speech": "noun"},
                    {"word": "strength", "phonetic": "/streŋθ/", "translation": "优势", "part_of_speech": "noun"},
                    {"word": "team player", "phonetic": "/tiːm ˈpleɪər/", "translation": "团队合作者", "part_of_speech": "noun phrase"},
                    {"word": "deadline", "phonetic": "/ˈdedlaɪn/", "translation": "截止日期", "part_of_speech": "noun"},
                    {"word": "salary expectation", "phonetic": "/ˈsæləri ˌekspekˈteɪʃən/", "translation": "薪资期望", "part_of_speech": "noun phrase"},
                ],
                "sentence_patterns": [
                    {"pattern": "I have ... years of experience in ...", "translation": "我在...方面有...年经验", "example": "I have five years of experience in web development."},
                    {"pattern": "My greatest strength is ...", "translation": "我最大的优势是...", "example": "My greatest strength is my ability to solve problems quickly."},
                ],
            },
            {
                "name": "Business Meeting",
                "description": "Practice participating in meetings, presenting ideas, and negotiating",
                "thumbnail_url": "/images/scenes/meeting.jpg",
                "role_prompt": "You are the team lead running a project meeting. Discuss project progress, gather updates, and make decisions with the team member. Keep the discussion focused and productive.",
                "opening_line": "Alright everyone, let's get started with our weekly project review. Could you begin by giving us an update on your tasks?",
                "difficulty_levels": ["intermediate", "advanced"],
                "tags": ["business", "meeting", "presentation"],
                "suggested_duration": 480,
                "vocabulary": [
                    {"word": "agenda", "phonetic": "/əˈdʒendə/", "translation": "议程", "part_of_speech": "noun"},
                    {"word": "deadline", "phonetic": "/ˈdedlaɪn/", "translation": "截止日期", "part_of_speech": "noun"},
                    {"word": "milestone", "phonetic": "/ˈmaɪlstəʊn/", "translation": "里程碑", "part_of_speech": "noun"},
                    {"word": "stakeholder", "phonetic": "/ˈsteɪkhəʊldər/", "translation": "利益相关者", "part_of_speech": "noun"},
                    {"word": "action item", "phonetic": "/ˈækʃən ˈaɪtəm/", "translation": "行动事项", "part_of_speech": "noun phrase"},
                ],
                "sentence_patterns": [
                    {"pattern": "I'd like to propose that we ...", "translation": "我建议我们...", "example": "I'd like to propose that we extend the deadline by a week."},
                    {"pattern": "Could you elaborate on ...?", "translation": "你能详细说明...吗？", "example": "Could you elaborate on the timeline for phase two?"},
                ],
            },
        ],
    },
]


async def seed_scenes(db: AsyncSession) -> None:
    """Insert seed categories, scenes, vocabulary, and sentence patterns if DB is empty."""
    result = await db.execute(select(SceneCategory).limit(1))
    if result.scalar_one_or_none() is not None:
        return  # Already seeded

    for cat_data in SEED_CATEGORIES:
        category = SceneCategory(
            name=cat_data["name"],
            icon_url=cat_data["icon_url"],
            sort_order=cat_data["sort_order"],
        )
        db.add(category)
        await db.flush()

        for sc_data in cat_data["scenes"]:
            vocab = sc_data.get("vocabulary", [])
            patterns = sc_data.get("sentence_patterns", [])
            scene = Scene(
                category_id=category.id,
                name=sc_data["name"],
                description=sc_data["description"],
                thumbnail_url=sc_data.get("thumbnail_url"),
                role_prompt=sc_data["role_prompt"],
                opening_line=sc_data["opening_line"],
                difficulty_levels=json.dumps(sc_data.get("difficulty_levels", ["beginner"])),
                tags=json.dumps(sc_data.get("tags", [])),
                suggested_duration=sc_data.get("suggested_duration", 300),
                is_active=True,
            )
            db.add(scene)
            await db.flush()

            for v in vocab:
                db.add(SceneVocabulary(
                    scene_id=scene.id,
                    word=v["word"],
                    phonetic=v.get("phonetic"),
                    translation=v.get("translation"),
                    part_of_speech=v.get("part_of_speech"),
                ))

            for p in patterns:
                db.add(SceneSentencePattern(
                    scene_id=scene.id,
                    pattern=p["pattern"],
                    translation=p.get("translation"),
                    example=p.get("example"),
                ))

    await db.commit()