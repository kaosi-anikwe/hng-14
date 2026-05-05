# generate_test_csv.py
import csv
import random

GENDERS = ['male', 'female']
AGE_GROUPS = ['child', 'teenager', 'adult', 'senior']
COUNTRIES = [
    ('NG', 'Nigeria'), ('US', 'United States'), ('GH', 'Ghana'),
    ('GB', 'United Kingdom'), ('ZA', 'South Africa'), ('KE', 'Kenya'),
    ('IN', 'India'), ('CA', 'Canada'), ('AU', 'Australia'), ('DE', 'Germany'),
    ('FR', 'France'), ('BR', 'Brazil'), ('JP', 'Japan'), ('CN', 'China'),
    ('EG', 'Egypt'), ('ET', 'Ethiopia'), ('TZ', 'Tanzania'), ('UG', 'Uganda'),
    ('SN', 'Senegal'), ('CI', "Cote d'Ivoire"),
]

FIRST_NAMES = [
    'Amara','Bolu','Chidi','Dayo','Emeka','Funmi','Gbenga','Hauwa','Ifeoma',
    'Jide','Kemi','Lola','Musa','Ngozi','Ola','Pita','Qudus','Remi','Sola',
    'Tunde','Uche','Voke','Wale','Xola','Yemi','Zara','Adaeze','Babatunde',
    'Chiamaka','Dimma','Efosa','Folake','Godwin','Helen','Ikenna','Jumoke',
    'Kunle','Lawal','Mercy','Nkem','Obiora','Patience','Rasheed','Seun',
    'Toyin','Udoka','Victor','Wunmi','Ximena','Yvonne','Zainab','Ahmed',
    'Blessing','Cynthia','David','Esther','Felix','Grace','Henry','Irene',
    'James','Kehinde','Lydia','Moses','Nora','Onome','Precious','Queen',
    'Richard','Susan','Timothy','Usman','Vivian','William','Xerxes','Yusuf',
]

LAST_NAMES = [
    'Okonkwo','Adesanya','Mensah','Osei','Diallo','Traore','Kamara',
    'Ibrahim','Musa','Yusuf','Adekunle','Bakare','Chukwu','Dada',
    'Eze','Fashola','Ganiyu','Hassan','Idowu','Johnson','Kalu',
    'Lawal','Mba','Nwosu','Ogundele','Peters','Quadri','Raji',
    'Salami','Taiwo','Usman','Vincent','Williams','Xavier','Yakubu',
]

def get_age_group(age):
    if age <= 12: return 'child'
    if age <= 19: return 'teenager'
    if age <= 59: return 'adult'
    return 'senior'

rows = 500_000  # Change to 500000 for a stress test

# Error injection config — approximate counts
ERROR_COUNTS = {
    "missing_field": 300,    # rows with a required field blanked out
    "invalid_age": 200,      # age < 0 or > 120
    "invalid_country": 150,  # bad alpha-2 country code
    "duplicate_name": 100,   # names repeated later in the file
}
INVALID_COUNTRY_CODES = ['XX', 'ZZ', 'QQ', '00', 'UK', 'EU']

total_errors = sum(ERROR_COUNTS.values())
error_slots = set(random.sample(range(rows), total_errors))
error_iter = iter(error_slots)

# Assign error slots to each type
missing_slots  = set(list(error_slots)[:ERROR_COUNTS["missing_field"]])
age_slots      = set(list(error_slots)[ERROR_COUNTS["missing_field"]:ERROR_COUNTS["missing_field"]+ERROR_COUNTS["invalid_age"]])
country_slots  = set(list(error_slots)[ERROR_COUNTS["missing_field"]+ERROR_COUNTS["invalid_age"]:ERROR_COUNTS["missing_field"]+ERROR_COUNTS["invalid_age"]+ERROR_COUNTS["invalid_country"]])
dup_slots      = set(list(error_slots)[-ERROR_COUNTS["duplicate_name"]:])

seen_names = set()
dup_name_pool = []  # names we'll reuse for duplicates

MISSING_FIELDS = ['name', 'gender', 'age', 'country_id', 'country_name']

with open('test_profiles.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'name','gender','gender_probability','age','age_group',
        'country_id','country_name','country_probability'
    ])
    writer.writeheader()

    written = 0
    attempts = 0

    while written < rows:
        attempts += 1
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first.lower()} {last.lower()} {attempts}"

        if name in seen_names:
            continue
        seen_names.add(name)

        gender = random.choice(GENDERS)
        age = random.randint(1, 85)
        country_code, country_name = random.choice(COUNTRIES)

        row = {
            'name': name,
            'gender': gender,
            'gender_probability': round(random.uniform(0.6, 0.99), 4),
            'age': age,
            'age_group': get_age_group(age),
            'country_id': country_code,
            'country_name': country_name,
            'country_probability': round(random.uniform(0.5, 0.95), 4),
        }

        # Inject errors based on slot assignment
        if written in missing_slots:
            row[random.choice(MISSING_FIELDS)] = ''       # blank out a required field
        elif written in age_slots:
            row['age'] = random.choice([-5, -1, 121, 150, 999])  # out-of-range age
        elif written in country_slots:
            row['country_id'] = random.choice(INVALID_COUNTRY_CODES)  # bad country code
        elif written in dup_slots:
            if dup_name_pool:
                row['name'] = random.choice(dup_name_pool)   # reuse an existing name
            # else fall through as a valid row (pool not built yet)

        # Keep a pool of early valid names for later duplication
        if written < rows // 2 and written not in (missing_slots | age_slots | country_slots | dup_slots):
            dup_name_pool.append(row['name'])

        writer.writerow(row)
        written += 1

total_injected = len(missing_slots) + len(age_slots) + len(country_slots) + len(dup_slots)
print(f"Done! Generated {written} rows in test_profiles.csv")
print(f"  ~{len(missing_slots)} missing-field rows")
print(f"  ~{len(age_slots)} invalid-age rows")
print(f"  ~{len(country_slots)} invalid-country rows")
print(f"  ~{len(dup_slots)} duplicate-name rows")
