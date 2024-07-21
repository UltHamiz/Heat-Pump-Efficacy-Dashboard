import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from shiny import App, Inputs, Outputs, Session, reactive, render, req, ui

# API stuff
import openmeteo_requests
import requests_cache
from retry_requests import retry

# Map stuff
from ipyleaflet import Map, Marker
from shinywidgets import output_widget, render_widget


df = pd.read_csv("data/cities.csv")
cities = df["city_state"].unique().tolist()

lat = df[df["city_state"] == "Urbana, Illinois"]["lat"].tolist()[0]

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize("city", "City",cities, selected="Urbana, Illinois"),
        ui.output_text("text", inline=True),
        ui.input_date_range("daterange", "Dates", start="2022-01-01", end="2024-01-01", min="2020-01-01", max="2024-01-01"),
        ui.input_radio_buttons( "tempunits",  "Units",  {"fahrenheit": "Fahrenheit", "celsius": "Celsius"}),  
        ui.input_slider("plotTemp", "Plot Temperature", -15, 50, 5),
        ui.input_checkbox_group( "plotOptions",  "Plot Options",  {"weekly": "Weekly Rolling Average", "monthly": "Monthly Rolling Average"}), 
        ui.input_slider("tableTemp", "Table Temperatures", min=-25, max=60, value=[0, 15]), 
        ui.page_fluid(output_widget("map", height=200, fillable=True)),
        open="always",
        width=350
	),
    ui.navset_tab(
        ui.nav_panel("Historical", 
                     ui.output_plot("plot"),
                     ui.output_data_frame("hist_table")),
        ui.nav_panel("About",
                     ui.markdown(
                        """
                        **Background**

                        Heat pumps are an alternative heating solution meant to be a subsitute for furnaces, but they can fail to operate under low temperatures. This application serves
                        as way for consumers to understand the historical weather trends across cities in the US to figure out if a heat pump is viable for them.
                        The historical weather data of the application is sourced from Open-Meteo API and the location data is from SimpleMaps

                        **Usage**

                        For interacting with the application, the following inputs can be changed by the user:
                        - City
                        - Dates (Interval of date Ranges to get weather data)
                        - Units (Celsius and Fahrenheit)
                        - Plot Temperature (Creates a horizontal line on the plot, changing colors for data points above/below)
                        - Plot Options (Creates line graphs on top of plot depicting the rolling average of temperature, weekly and monthly respectively)
                        - Table Temperature (Selection of range of temperature to be shown on the table below plot)


                        **Citations**
                        
                        Weather Data:\n
                        Zippenfenig, P. (2023). Open-Meteo.com Weather API [Computer software]. Zenodo. https://doi.org/10.5281/ZENODO.7970649

                        Hersbach, H., Bell, B., Berrisford, P., Biavati, G., Horányi, A., Muñoz Sabater, J., Nicolas, J., Peubey, C., Radu, R., Rozum, I., Schepers, D., Simmons, A., Soci, C., Dee, D., Thépaut, J-N. (2023). ERA5 hourly data on single levels from 1940 to present [Data set]. ECMWF. https://doi.org/10.24381/cds.adbb2d47

                        Muñoz Sabater, J. (2019). ERA5-Land hourly data from 2001 to present [Data set]. ECMWF. https://doi.org/10.24381/CDS.E2161BAC

                        Schimanke S., Ridal M., Le Moigne P., Berggren L., Undén P., Randriamampianina R., Andrea U., Bazile E., Bertelsen A., Brousseau P., Dahlgren P., Edvinsson L., El Said A., Glinton M., Hopsch S., Isaksson L., Mladek R., Olsson E., Verrelle A., Wang Z.Q. (2021). CERRA sub-daily regional reanalysis data for Europe on single levels from 1984 to present [Data set]. ECMWF. https://doi.org/10.24381/CDS.622A565A

                        Location Data:\n
                        https://simplemaps.com/data/us-cities

                        (Created by Hamiz Anjum)
                        """
                     )),
        id="tab",
    ),
    # ui.card(
    #     ui.output_plot("plot"),
    #     ui.output_data_frame("hist_table"),
	# ),
    title="Daily Heat Pump Efficiency Counter"

    
)  

def server(input, output, session):

    @reactive.calc
    def apiresponse():
        # Setup the Open-Meteo API client with cache and retry on error
        cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
        retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
        openmeteo = openmeteo_requests.Client(session = retry_session)

        # Make sure all required weather variables are listed here
        # The order of variables in hourly or daily is important to assign them correctly below
        url = "https://archive-api.open-meteo.com/v1/archive"
     
        #getting inputs (to be used in params)
        start_date = input.daterange()[0]
        end_date = input.daterange()[1]

        req(input.city())

        lat = df[df["city_state"] == input.city()]["lat"].tolist()[0]
        long = df[df["city_state"] == input.city()]["lng"].tolist()[0]

        temp_units = input.tempunits()

        params = {
            "latitude": lat,               # input
            "longitude": long,              # input
            "start_date": start_date,      # input
            "end_date": end_date,        # input
            "daily": "temperature_2m_min",   # fixed
            "temperature_unit": temp_units # input
        }
        responses = openmeteo.weather_api(url, params=params)

        # Process first location. Add a for-loop for multiple locations or weather models
        response = responses[0]
        return response


    @reactive.Calc
    def filter_df():
        response = apiresponse()

        # Process hourly data. The order of variables needs to be the same as requested.
        hourly = response.Daily()
        hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()

        hourly_data = {"date": pd.date_range(
            start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
            end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
            freq = pd.Timedelta(seconds = hourly.Interval()),
            inclusive = "left"
        )}
        hourly_data["temperature_2m_min"] = hourly_temperature_2m

        hourly_dataframe = pd.DataFrame(data = hourly_data)

        return hourly_dataframe
    

    @render.text
    def text():
        response = apiresponse()
        return f"{round(response.Latitude(), 4)}°N, {round(response.Longitude(),4)}°E"
    
    @reactive.effect
    def updateslider():
        ui.update_slider("plotTemp", value=(5 if input.tempunits() == "fahrenheit" else -15),
                         min = (-15 if input.tempunits() == "fahrenheit" else -25),
                         max =(50 if input.tempunits() == "fahrenheit" else 10))
        ui.update_slider("tableTemp", value =([0,15] if input.tempunits()== "fahrenheit" else [-20,-10]), 
                         min = (-25 if input.tempunits() == "fahrenheit" else -30),
                         max =(60 if input.tempunits() == "fahrenheit" else 15) )
    

    @render_widget  
    def map():
        response = apiresponse()
        lat = response.Latitude()
        long = response.Longitude()
        m = Map(center=(lat, long), zoom=12)
        m.add(Marker(location=(lat, long)))
        return m
       


    @render.data_frame
    def hist_table():
        histdf = filter_df()

        df = pd.DataFrame({"Temp": np.arange(input.tableTemp()[1], input.tableTemp()[0] - 1, -1)})
        # df["val" == 0]
        vallist = df["Temp"].tolist()
        
        tmp = []
        for i in vallist:
            tmp.append(len(histdf[histdf["temperature_2m_min"] < i]))
        df["Days Below"] = tmp
        df["Proportion Below"] = round(df["Days Below"]/len(histdf), 3)  


        return render.DataGrid(df, height="auto", width="100%")
        # df = pd.DataFrame()



    # @output
    @render.plot(alt="A Scatterplot")
    def plot():
        # plotting stuff
        df = filter_df()

        # rolling average data
        df["weekrollingavg"] = df["temperature_2m_min"].rolling(window=7).mean()
        df["monthrollingavg"] = df["temperature_2m_min"].rolling(window=30).mean()

        
        #main scatter plot
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots()
        # sns.scatterplot(data=df, x="date", y="temperature_2m_min", ax=ax, color="black")

        # seperate plots for points above and below the input slider temperature (horizontal line)
        upper = df[df["temperature_2m_min"] >= input.plotTemp()]
        lower = df[df["temperature_2m_min"] < input.plotTemp()]

        #plot temperature slider line
        plt.axhline(y=input.plotTemp(), color="darkgray")

        sns.scatterplot(data=upper, x="date", y="temperature_2m_min", ax=ax, color="black")
        sns.scatterplot(data=lower, x="date", y="temperature_2m_min", ax=ax, color="lightgray")



        #plot options
        if ("weekly" in  input.plotOptions()):
            sns.lineplot(data=df, x="date", y ="weekrollingavg" , ax=ax, color="orange")
        if ("monthly" in input.plotOptions()):
            sns.lineplot(data=df, x="date", y ="monthrollingavg" , ax=ax, color="blue")
        
        if (input.tempunits() == "fahrenheit"):
            ax.set(xlabel='', ylabel='Daily Minimum Temperature °F')
        else:
            ax.set(xlabel='', ylabel='Daily Minimum Temperature °C')




        return fig



app = App(app_ui, server)

