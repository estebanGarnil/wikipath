import unittest
from prepare_text import prepare


class PreparationTests(unittest.TestCase):
    def test_dates_centuries_and_nested_language(self):
        result = prepare("Paul, né le {{date de naissance|11|novembre|1866}}, au {{s|XIX}}, {{lang|fr|texte={{nobr|un linguiste}}}}.", 'Paul')
        self.assertIn('11 novembre 1866', result['text'])
        self.assertIn('XIXe siècle', result['text'])
        self.assertIn('un linguiste', result['text'])

    def test_math_retained(self):
        result = prepare(r'Le produit de <math>x</math> et {{math|y}} est <math>x \cdot y</math>.', 'Produit')
        self.assertIn('de x et y', result['text'])
        self.assertIn(r'x \cdot y', result['text'])

    def test_noise_removed(self):
        result = prepare('{{Infobox|nom=BRUIT}}Une personne.<ref>REFERENCE</ref>[[Fichier:X.jpg|IMAGE]]', 'Personne')
        self.assertEqual(result['text'], 'Une personne.')
        self.assertIn('infobox', result['omitted_templates'])

    def test_short_lead_completed(self):
        result = prepare('Un linguiste.\n== Biographie ==\n\n' + 'Il étudie les langues anciennes et leurs transformations. ' * 4, 'Personne')
        self.assertTrue(result['supplemented'])
        self.assertEqual(result['introduction'], 'Un linguiste.')
        self.assertIn('langues anciennes', result['text'])

    def test_references_and_subsections_excluded(self):
        result = prepare('Bref.\n== Notes et références ==\n\n' + 'REFERENCE ' * 30 + '\n=== Détails ===\n\n' + 'REFERENCE ' * 30, 'Sujet')
        self.assertEqual(result['text'], 'Bref.')

    def test_disambiguation_not_supplemented(self):
        result = prepare('{{Homonymie}}Plusieurs sens.\n== Détails ==\n\n' + 'Une explication longue. ' * 20, 'Terme')
        self.assertTrue(result['is_disambiguation'])
        self.assertFalse(result['supplemented'])

    def test_empty_and_heading_first(self):
        self.assertTrue(prepare('', 'Vide')['title_only'])
        result = prepare('== Histoire ==\n\n' + 'Une longue histoire de cette discipline. ' * 5, 'Sujet')
        self.assertEqual(result['introduction'], '')
        self.assertTrue(result['supplemented'])

    def test_long_lead_not_supplemented(self):
        result = prepare('Une introduction complète. ' * 30 + '\n== Suite ==\n\nAUTRE TEXTE ' * 30, 'Sujet')
        self.assertFalse(result['supplemented'])
        self.assertNotIn('AUTRE TEXTE', result['text'])


if __name__ == '__main__':
    unittest.main()
