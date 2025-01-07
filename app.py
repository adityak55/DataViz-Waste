from flask import Flask, render_template, jsonify, request
import pandas as pd
import folium
from geopy.geocoders import Nominatim
import os
import json
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

def get_lat_long(county_name, state_abbr):
    geolocator = Nominatim(user_agent="waste-disposal-app")
    location = geolocator.geocode(f"{county_name}, {state_abbr}")
    if location:
        return location.latitude, location.longitude
    return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/choropleth_data')
def choropleth_data():
    # Verify GeoJSON file path
    file_path = 'california-counties.geojson'
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return jsonify({"error": f"GeoJSON file not found: {file_path}"}), 500
    
    # Read the CSV file
    df = pd.read_csv('waste_dataset.csv')
    
    # Group by 'Countyname' and sum 'DisposalTons'
    df_grouped = df.groupby("Countyname")['DisposalTons'].sum().reset_index()
    
    # Sort the DataFrame by 'DisposalTons' and select the top 5 counties
    top_5_df = df_grouped.nlargest(5, 'DisposalTons')
    
    # Get latitude and longitude for each county
    top_5_df['lat_lon'] = top_5_df.apply(lambda row: get_lat_long(row['Countyname'], 'CA'), axis=1)
    
    # Filter out rows without valid latitude and longitude
    top_5_df = top_5_df.dropna(subset=['lat_lon'])
    
    # Split the lat_lon tuple into separate latitude and longitude columns
    top_5_df[['Latitude', 'Longitude']] = pd.DataFrame(top_5_df['lat_lon'].tolist(), index=top_5_df.index)
    
    # Debugging: Print the data being used for plotting
    print("Data used for plotting:")
    print(top_5_df)

    try:
        # Generate the map centered around California
        m = folium.Map(location=[37.7749, -122.4194], zoom_start=6)

        # Add the GeoJSON overlay for California counties with no borders
        with open(file_path) as f:
            counties_geojson = json.load(f)

        folium.GeoJson(
            counties_geojson,
            name='geojson',
            style_function=lambda x: {'fillColor': 'transparent', 'color': 'transparent'}
        ).add_to(m)

        # Calculate the bounds of the GeoJSON to fit the map
        bounds = folium.GeoJson(counties_geojson).get_bounds()
        m.fit_bounds(bounds)

        # Add circles to the map
        for _, row in top_5_df.iterrows():
            folium.CircleMarker(
                location=[row['Latitude'], row['Longitude']],
                radius=row['DisposalTons'] / 10000,  # Adjust scaling factor as needed
                popup=f"<a href='/county_info?county={row['Countyname']}' target='_blank'>{row['Countyname']}: {round(row['DisposalTons'], 2)} tons</a>",
                color='blue',
                fill=True,
                fill_color='blue'
            ).add_to(m)

        folium.LayerControl().add_to(m)

        # Save the map as an HTML file
        m.save('templates/map.html')

        return render_template('map.html')
    except Exception as e:
        print(f"Error generating map: {e}")
        return jsonify({"error": "Failed to generate map"}), 500

@app.route('/county_info', methods=['GET'])
def county_info():
    county_name = request.args.get('county')
    df = pd.read_csv('waste_dataset.csv')
    county_data = df[df['Countyname'] == county_name]
    county_data.fillna(0, inplace=True)
    county_data = county_data.groupby('AgencyType')['DisposalTons'].sum().reset_index()
    
    if county_data.empty:
        return jsonify({"error": "No data found for the specified county"}), 404

    # Generate bar plot
    plt.figure(figsize=(10, 6))
    plt.bar(county_data['AgencyType'], county_data['DisposalTons'], color='skyblue')
    plt.xlabel('Agency Type')
    plt.ylabel('Disposal Tons')
    plt.title(f'Disposal Tons by Agency Type for {county_name}')
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save plot to a bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()
    plt.close()

    return render_template('county_info.html', county_name=county_name, plot_image=image_base64)

if __name__ == '__main__':
    app.run(debug=True)
