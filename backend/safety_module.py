# safety_module.py
def check_abuse_harassment(text):
    text = text.lower()

    abuse_words = [
        # core violence / abuse terms
        "harass", "harassment", "abuse", "abused", "abusing",
        "assault", "sexual assault", "molest", "molested", "molesting",
        "domestic violence", "beating me", "beating him", "beating her",
        "hit me", "hitting me", "hitting him", "hitting her",
        "rape", "raped", "attempted rape", "sexual abuse",
        "unsafe at home", "not safe at home", "not safe here",
        "stalk", "stalking", "threaten", "threatening", "threatened",
        "blackmail", "blackmailed",
        "child abuse", "child sexual abuse",
        "bullying", "cyberbullying", "online harassment",
    ]

    if any(word in text for word in abuse_words):
        return True
    return False


def abuse_support_message():
    return (
        "I'm really sorry you're going through this. No one should have to feel unsafe, and everyone deserve support and protection.\n\n"
        "In India, you can reach out for immediate help:\n"
        "• Women Helpline (all‑India, 24/7): 181\n"
	"• Police emergency (pan‑India): 112 (or 100)\n"
        "• National Commission for Women (NCW) helpline: 14490\n"
        "• CHILDLINE (for children under 18): 1098\n"
        "• iCall (counselling, all ages): +91 9152987821\n\n"
        "If you or someone else is in immediate danger, please call 112 or 100 right away.\n\n"
        "You are not alone, and there are people who can help you stay safe."
    )
