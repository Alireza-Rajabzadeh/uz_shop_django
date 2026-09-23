from core.management.seeders.base import BaseSeeder
from domains.banks.models import Bank


class BankSeeder(BaseSeeder):
    ACCOUNT_NUMBER_REGEX = r"^\d{10,24}$"
    SHEBA_REGEX = r"^IR\d{24}$"

    BANKS = [
        {"id": 100, "name": "National Bank of Iran", "fa_name": "بانک ملی ایران", "card_number_regex": r"^603799\d{10}$"},
        {"id": 101, "name": "Sepah Bank", "fa_name": "بانک سپه", "card_number_regex": r"^589210\d{10}$"},
        {"id": 102, "name": "Export Development Bank of Iran", "fa_name": "بانک توسعه صادرات", "card_number_regex": r"^627648\d{10}$"},
        {"id": 103, "name": "Bank of Industry and Mine", "fa_name": "بانک صنعت و معدن", "card_number_regex": r"^627961\d{10}$"},
        {"id": 104, "name": "Agricultural Bank", "fa_name": "بانک کشاورزی", "card_number_regex": r"^603770\d{10}$"},
        {"id": 105, "name": "Bank Maskan", "fa_name": "بانک مسکن", "card_number_regex": r"^628023\d{10}$"},
        {"id": 106, "name": "Post Bank of Iran", "fa_name": "پست بانک ایران", "card_number_regex": r"^627760\d{10}$"},
        {"id": 107, "name": "Tosee Taavon Bank", "fa_name": "بانک توسعه تعاون", "card_number_regex": r"^502908\d{10}$"},
        {"id": 108, "name": "Eghtesad Novin Bank", "fa_name": "بانک اقتصاد نوین", "card_number_regex": r"^627412\d{10}$"},
        {"id": 109, "name": "Parsian Bank", "fa_name": "بانک پارسیان", "card_number_regex": r"^(622106|639194|627884)\d{10}$"},
        {"id": 110, "name": "Pasargad Bank", "fa_name": "بانک پاسارگاد", "card_number_regex": r"^502229\d{10}$"},
        {"id": 111, "name": "Karafarin Bank", "fa_name": "بانک کارآفرین", "card_number_regex": r"^627488\d{10}$"},
        {"id": 112, "name": "Saman Bank", "fa_name": "بانک سامان", "card_number_regex": r"^621986\d{10}$"},
        {"id": 113, "name": "Sina Bank", "fa_name": "بانک سینا", "card_number_regex": r"^639346\d{10}$"},
        {"id": 114, "name": "Sarmayeh Bank", "fa_name": "بانک سرمایه", "card_number_regex": r"^639607\d{10}$"},
        {"id": 115, "name": "Ayandeh Bank", "fa_name": "بانک آینده", "card_number_regex": r"^636214\d{10}$"},
        {"id": 116, "name": "City Bank", "fa_name": "بانک شهر", "card_number_regex": r"^(502806|504706)\d{10}$"},
        {"id": 117, "name": "Day Bank", "fa_name": "بانک دی", "card_number_regex": r"^502938\d{10}$"},
        {"id": 118, "name": "Bank Saderat Iran", "fa_name": "بانک صادرات ایران", "card_number_regex": r"^603769\d{10}$"},
        {"id": 119, "name": "Mellat Bank", "fa_name": "بانک ملت", "card_number_regex": r"^610433\d{10}$"},
        {"id": 120, "name": "Tejarat Bank", "fa_name": "بانک تجارت", "card_number_regex": r"^627353\d{10}$"},
        {"id": 121, "name": "Refah Kargaran Bank", "fa_name": "بانک رفاه کارگران", "card_number_regex": r"^589463\d{10}$"},
        {"id": 122, "name": "Ansar Bank", "fa_name": "بانک انصار", "card_number_regex": r"^627381\d{10}$"},
        {"id": 123, "name": "Iran Zamin Bank", "fa_name": "بانک ایران زمین", "card_number_regex": r"^505785\d{10}$"},
        {"id": 124, "name": "Central Bank of Iran", "fa_name": "بانک مرکزی", "card_number_regex": r"^636795\d{10}$"},
        {"id": 125, "name": "Hekmat Iranian Bank", "fa_name": "بانک حکمت ایرانیان", "card_number_regex": r"^636949\d{10}$"},
        {"id": 126, "name": "Gardeshgari Bank", "fa_name": "بانک گردشگری", "card_number_regex": r"^505416\d{10}$"},
        {"id": 127, "name": "Mehr Iran Bank", "fa_name": "بانک قرض الحسنه مهر ایران", "card_number_regex": r"^606373\d{10}$"},
        {"id": 128, "name": "Tosee Credit Institution", "fa_name": "موسسه اعتباری توسعه", "card_number_regex": r"^628157\d{10}$"},
        {"id": 129, "name": "Kosar Credit Institution", "fa_name": "موسسه مالی و اعتباری کوثر", "card_number_regex": r"^505801\d{10}$"},
        {"id": 130, "name": "Mehr Credit Institution", "fa_name": "موسسه مالی و اعتباری مهر", "card_number_regex": r"^639370\d{10}$"},
        {"id": 131, "name": "Ghavamin Bank", "fa_name": "بانک قوامین", "card_number_regex": r"^639599\d{10}$"},
    ]

    def run(self):
        for record in self.BANKS:
            Bank.objects.update_or_create(
                id=record["id"],
                defaults={
                    "name": record["name"],
                    "fa_name": record["fa_name"],
                    "card_number_regex": record["card_number_regex"],
                    "account_number_regex": self.ACCOUNT_NUMBER_REGEX,
                    "sheba_regex": self.SHEBA_REGEX,
                    "is_active": True,
                },
            )
