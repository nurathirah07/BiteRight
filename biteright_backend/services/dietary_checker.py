# services/dietary_checker.py
"""
Service to check ingredients against user's dietary profile
"""

from dietary_options import ALLERGEN_OPTIONS, DIETARY_OPTIONS

class DietaryChecker:
    def __init__(self):
        self.allergen_map = self._create_allergen_map()
        self.dietary_map = self._create_dietary_map()
    
    def _create_allergen_map(self):
        """Create a mapping of allergen IDs to their details"""
        return {a['id']: a for a in ALLERGEN_OPTIONS}
    
    def _create_dietary_map(self):
        """Create a mapping of diet IDs to their details"""
        return {d['id']: d for d in DIETARY_OPTIONS}
    
    def check_ingredients(self, ingredients_text, user_allergies, user_diets):
        """
        Check ingredients against user's profile
        Returns detailed results with violations
        """
        ingredients_lower = ingredients_text.lower()
        
        results = {
            'safe': True,
            'violations': [],
            'warnings': [],
            'details': {
                'allergens_found': [],
                'dietary_violations': []
            }
        }
        
        # Check allergens
        for allergy_id in user_allergies:
            if allergy_id in self.allergen_map:
                allergen = self.allergen_map[allergy_id]
                
                # Check synonyms
                for synonym in allergen.get('synonyms', []):
                    if synonym.lower() in ingredients_lower:
                        violation = {
                            'type': 'allergen',
                            'restriction_id': allergy_id,
                            'restriction_name': allergen['label'],
                            'found': synonym,
                            'severity': allergen.get('severity', 'medium'),
                            'message': f"Contains {synonym} which is {allergen['label']}"
                        }
                        results['violations'].append(violation)
                        results['details']['allergens_found'].append(violation)
                        results['safe'] = False
        
        # Check dietary restrictions
        for diet_id in user_diets:
            if diet_id in self.dietary_map:
                diet = self.dietary_map[diet_id]
                
                # Check forbidden ingredients
                for forbidden in diet.get('forbidden', []):
                    if forbidden.lower() in ingredients_lower:
                        violation = {
                            'type': 'dietary',
                            'restriction_id': diet_id,
                            'restriction_name': diet['label'],
                            'found': forbidden,
                            'severity': 'medium',
                            'message': f"Contains {forbidden} which violates {diet['label']} restrictions"
                        }
                        results['violations'].append(violation)
                        results['details']['dietary_violations'].append(violation)
                        results['safe'] = False
        
        # Determine overall risk level
        if results['violations']:
            high_severity = any(v['severity'] == 'high' for v in results['violations'])
            results['risk_level'] = 'unsafe' if high_severity else 'caution'
        else:
            results['risk_level'] = 'safe'
        
        return results