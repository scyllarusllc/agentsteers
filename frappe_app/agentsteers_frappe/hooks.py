app_name = "agentsteers_frappe"
app_title = "AgentSteers"
app_publisher = "AgentSteers Contributors"
app_description = "Task history, connections, and settings for AgentSteers"
app_email = ""
app_license = "License pending; see repository"
required_apps = ["frappe"]

# Route the root domain to the Frappe-hosted landing page.
home_page = "index"

# Style Frappe website login/signup forms without replacing authentication routes.
web_include_css = ["/assets/agentsteers_frappe/css/login.css"]
