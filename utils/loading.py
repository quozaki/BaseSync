import json
import csv

def load_units():
    with open("data/units_prices_and_time.json", 'r') as f:
        return json.load(f)
    
def load_rates():
    data = {}
    with open("data/base_production_rate.csv", 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[int(row['Bases'])] = float(row['Rate'])
    return data