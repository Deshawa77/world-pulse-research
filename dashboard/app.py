import dash
from dash import html

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("World Pulse Dashboard"),
    html.P("This is a placeholder for visualizations")
])

if __name__ == "__main__":
    app.run_server(debug=True)
