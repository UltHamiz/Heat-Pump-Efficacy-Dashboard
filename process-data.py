import pandas as pd

df = pd.read_csv("data-raw/uscities.csv")

# only keep cities with population above 10000
df = df[df["population"] >= 10000]

#add city_state column
df["city_state"] = df["city"] + ', ' + df["state_name"]

# Select city_state, lat, and lng columnbs
df = df[["city_state", "lat", "lng"]]
# print(df)

# write to csv
df.to_csv("data/cities.csv", index=False)

