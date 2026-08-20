"""
Context-aware labels for the Organization -> Branch -> Classification ->
Section -> Member hierarchy.

`Classification`/`Section` are the neutral internal names (unchanged in the
database and in Python — renaming the model layer across the whole app would
be the "dangerous model rename" the spec explicitly warns against). This
module only controls what a user *reads* on screen: a Classification is a
"Class" to a school and a "Department" to an office, without either org ever
knowing the other label exists.

Deliberately small — it swaps the two nouns the spec calls out by name
(Classification, Section), not "Member"/"Student", which stays "Member"
everywhere since staff and students are both members and a blanket swap
would be wrong for either org type.
"""

from school.features import has_feature


def get_terms(org):
    """Return the label set for `org`. `student_mgmt` on == education wording."""
    education = has_feature(org, 'student_mgmt') if org is not None else True
    if education:
        return {
            'classification': 'Class', 'classification_plural': 'Classes',
            'section': 'Section', 'section_plural': 'Sections',
            'structure_page_title': 'Classes & Sections',
            'structure_page_subtitle': 'Branches · Classes · Sections',
        }
    return {
        'classification': 'Department', 'classification_plural': 'Departments',
        'section': 'Team', 'section_plural': 'Teams',
        'structure_page_title': 'Departments & Teams',
        'structure_page_subtitle': 'Branches · Departments · Teams',
    }
