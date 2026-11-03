import re


class QuestionParser:

    # =====================================================
    # PARSE QUESTION
    # =====================================================

    def parse(
        self,
        question: str,
        catalog_tables: list[dict],
    ) -> dict:

        question_lower = question.lower()

        # -------------------------------------------------
        # FIND TABLE
        # -------------------------------------------------

        selected_table = None

        for table in catalog_tables:

            table_name = table["name"].lower()

            if table_name in question_lower:

                selected_table = table

                break

        # -------------------------------------------------
        # CUSTOMER KEYWORDS
        # -------------------------------------------------

        if selected_table is None:

            if (
                "مشتری" in question
                or "مشتری‌ها" in question
                or "مشتریان" in question
                or "customer" in question_lower
            ):

                for table in catalog_tables:

                    if table["name"].lower() == "customers":

                        selected_table = table

                        break

        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------

        if selected_table is None:

            return {
                "success": False,
                "error": "Could not identify table",
                "table": None,
                "where": None,
            }

        # -------------------------------------------------
        # CITY
        # -------------------------------------------------

        city = self.extract_city(
            question
        )

        where = None

        if city:

            where = (
                f"[city] = "
                f"N'{self.escape_value(city)}'"
            )

        return {
            "success": True,
            "table": selected_table,
            "where": where,
        }

    # =====================================================
    # EXTRACT CITY
    # =====================================================

    def extract_city(
        self,
        question: str,
    ) -> str | None:

        cities = [
            "تهران",
            "مشهد",
            "اصفهان",
            "شیراز",
            "تبریز",
            "کرج",
            "قم",
            "رشت",
            "اهواز",
        ]

        for city in cities:

            if city in question:

                return city

        return None

    # =====================================================
    # ESCAPE VALUE
    # =====================================================

    def escape_value(
        self,
        value: str,
    ) -> str:

        return value.replace(
            "'",
            "''",
        )