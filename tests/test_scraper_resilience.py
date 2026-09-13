import unittest
from scraper import parse_ingredient_line, parse_raw_recipe_text, fallback_json_ld_scrape

class TestScraperResilience(unittest.TestCase):
    def test_ingredient_line_parsing(self):
        sample = parse_ingredient_line("1 1/2 cups heavy cream")
        self.assertEqual(sample["amount"], "1 1/2")
        self.assertEqual(sample["unit"], "cups")
        self.assertIn("cream", sample["name"])
        self.assertEqual(sample["category"], "Dairy")

        sample2 = parse_ingredient_line("2 tbsp minced garlic")
        self.assertEqual(sample2["amount"], "2")
        self.assertEqual(sample2["unit"], "tbsp")
        self.assertEqual(sample2["category"], "Produce")

    def test_raw_text_recipe_parsing(self):
        text = """Grandma's Chocolate Chip Cookies
The best soft and chewy chocolate chip cookies ever.

Ingredients
2 1/4 cups all-purpose flour
1 tsp baking soda
1 cup butter, softened
3/4 cup granulated sugar
2 cups semi-sweet chocolate chips

Instructions
1. Preheat oven to 375 degrees F.
2. Combine flour and baking soda in small bowl.
3. Beat butter and sugars until creamy.
4. Drop by rounded tablespoon onto ungreased baking sheets.
5. Bake for 9 to 11 minutes or until golden brown.
"""
        recipe = parse_raw_recipe_text(text)
        self.assertEqual(recipe["title"], "Grandma's Chocolate Chip Cookies")
        self.assertTrue(len(recipe["ingredients"]) >= 4)
        self.assertTrue(len(recipe["steps"]) >= 4)

    def test_pasted_html_extraction(self):
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "Quick Tomato Basil Pasta",
            "description": "Simple 15-minute weeknight dinner.",
            "recipeIngredient": ["1 lb penne", "2 cups marinara sauce", "1/4 cup fresh basil"],
            "recipeInstructions": ["Boil pasta in salted water.", "Toss with marinara sauce.", "Garnish with basil."]
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        recipe = parse_raw_recipe_text(html)
        self.assertEqual(recipe["title"], "Quick Tomato Basil Pasta")
        self.assertEqual(len(recipe["ingredients"]), 3)
        self.assertEqual(len(recipe["steps"]), 3)

if __name__ == "__main__":
    unittest.main()
