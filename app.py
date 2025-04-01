from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import math
import folium
from folium import FeatureGroup

app = Flask(__name__)

# Load the dataset

url = "https://drive.google.com/uc?export=download&id=16Z8dnSSZ4jFXaf1WQIvs5t70j5Iqeuxw"
df = pd.read_csv(url)

# Haversine formula to calculate distance between two coordinates in miles
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Radius of Earth in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c  # Distance in miles

# Define distance categories
def classify_distance(distance):
    if distance <= 10:
        return "Category 1 (≤10 miles)"
    elif distance <= 30:
        return "Category 2 (10-30 miles)"
    else:
        return "Category 3 (>30 miles)"

# Function to format the demographics data
def format_demographics(df_subset):
    demographics = {}

    if 'race' in df_subset.columns:
        # Get race distribution, capitalize the race names and calculate percentages
        race_distribution = df_subset['race'].value_counts(normalize=True).mul(100).to_dict()
        race_distribution = {k.capitalize(): f"{v:.1f}%" for k, v in race_distribution.items()}
        demographics['race_distribution'] = race_distribution

    if 'gender' in df_subset.columns:
        # Get gender distribution and calculate percentages
        gender_distribution = df_subset['gender'].value_counts(normalize=True).mul(100).to_dict()
        gender_distribution = {k: f"{v:.1f}%" for k, v in gender_distribution.items()}
        demographics['gender_distribution'] = gender_distribution

    if 'age' in df_subset.columns:
        demographics['average_age'] = round(df_subset['age'].mean(), 2)
    
    return demographics

@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/patient_distance_analysis')
def patient_distance_analysis():
    organizations = df[['oid', 'name']].drop_duplicates().to_dict(orient='records')
    years = df['year'].drop_duplicates().sort_values().tolist()  # Extract available years
    return render_template('index.html', organizations=organizations, years=years)  # This is your existing app page

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    year_filter = int(data.get('year', 2024))
    organization_id = data.get('organization_id')

    df_filtered = df[(df['year'] == year_filter) & (df['oid'] == organization_id)]
    
    if df_filtered.empty:
        return jsonify({'error': f'No data found for Organization ID {organization_id} in year {year_filter}'}), 400

    # Get organization details
    org_lat = df_filtered.iloc[0]['olat']
    org_lon = df_filtered.iloc[0]['olong']
    organization_name = df_filtered.iloc[0]['name']
    organization_address = f"{df_filtered.iloc[0]['address']}, {df_filtered.iloc[0]['city']}, {df_filtered.iloc[0]['state']} {df_filtered.iloc[0]['zip']}"

    # Calculate distances for patients
    df_patients = df[df['year'] == year_filter].copy()
    df_patients['distance_from_org'] = df_patients.apply(
        lambda row: haversine(row['plat'], row['plong'], org_lat, org_lon), axis=1
    )
    df_patients['distance_category'] = df_patients['distance_from_org'].apply(classify_distance)

    # Get unique patients by category
    patients_by_category = df_patients[df_patients['oid'] == organization_id].groupby('distance_category')['pid'].nunique()
    total_unique_patients = df_patients[df_patients['oid'] == organization_id]['pid'].nunique()

    # Category 1 (≤10 miles) analysis
    patients_category_1 = df_patients[df_patients['distance_category'] == "Category 1 (≤10 miles)"]
    total_unique_patients_category_1 = patients_category_1['pid'].nunique()
    patients_category_1_selected_org = patients_category_1[patients_category_1['oid'] == organization_id]
    total_unique_patients_selected_org = patients_category_1_selected_org['pid'].nunique()

    # Demographics
    demographics_category_1 = format_demographics(patients_category_1)
    demographics_category_1_selected_org = format_demographics(patients_category_1_selected_org)

    # Map visualization
    m = folium.Map(location=[org_lat, org_lon], zoom_start=9)

    distance_mapping = {
        "Category 1 (≤10 miles)": {'radius': 10 * 1609, 'color': 'green'},
        "Category 2 (10-30 miles)": {'radius': 30 * 1609, 'color': 'blue'},
        "Category 3 (>30 miles)": {'radius': 50 * 1609, 'color': 'purple'}
    }

    # Create layers
    distance_layer_1 = FeatureGroup(name='≤10 miles')
    distance_layer_2 = FeatureGroup(name='>10 and ≤30 miles')
    distance_layer_3 = FeatureGroup(name='>30 miles')
    org_layer = FeatureGroup(name='Organizations')

    folium.Marker(
        location=[org_lat, org_lon],
        popup=f"Selected Organization: {organization_name}",
        icon=folium.Icon(color='blue', icon='info-sign')
    ).add_to(org_layer)

    # Add other organizations
    for _, row in df[['name', 'olat', 'olong', 'oid']].drop_duplicates().iterrows():
        if row['oid'] != organization_id:
            folium.CircleMarker(
                location=[row['olat'], row['olong']],
                radius=3,
                color='red',
                fill=True,
                fill_color='red',
                fill_opacity=0.8,
                tooltip=row['name']
            ).add_to(org_layer)

    # Modify this loop to correctly handle the data structure
    for category, count in patients_by_category.items():
        if category in distance_mapping:
            circle = folium.Circle(
                location=[org_lat, org_lon],
                radius=distance_mapping[category]['radius'],
                color=distance_mapping[category]['color'],
                fill=True,
                fill_opacity=0.4,
                tooltip=f"Patients: {count}"
            )
            if category == "Category 3 (>30 miles)":
                circle.add_to(distance_layer_3)
            elif category == "Category 2 (10-30 miles)":
                circle.add_to(distance_layer_2)
            elif category == "Category 1 (≤10 miles)":
                circle.add_to(distance_layer_1)

    for layer in [distance_layer_3, distance_layer_2, distance_layer_1, org_layer]:
        if layer._children:
            layer.add_to(m)

    folium.LayerControl().add_to(m)
    map_html = m._repr_html_()

    return jsonify({
        'organization_id': organization_id,
        'organization_name': organization_name,
        'organization_address': organization_address,
        'total_unique_patients': total_unique_patients,
        'patient_inflow_by_category': patients_by_category.to_dict(),
        'total_patients_within_10_miles': total_unique_patients_category_1,
        'total_patients_visiting_selected_org': total_unique_patients_selected_org,
        'demographics_category_1': demographics_category_1,
        'demographics_category_1_selected_org': demographics_category_1_selected_org,
        'map_html': map_html
    })

if __name__ == '__main__':
    app.run(debug=True)
