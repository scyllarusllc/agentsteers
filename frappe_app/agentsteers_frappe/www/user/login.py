"""AgentSteers login route backed by Frappe's existing authentication flow."""
import frappe

no_cache = True
sitemap = False


def get_context(context):
    account = '/user/account'
    # Keep both password and OAuth logins on the same fixed local return path.
    if frappe.session.user != 'Guest':
        frappe.local.flags.redirect_location = account
        raise frappe.Redirect
    if frappe.local.request.args.get('redirect-to') != account:
        frappe.local.flags.redirect_location = '/user/login?redirect-to=%2Fuser%2Faccount'
        raise frappe.Redirect
    from frappe.www.login import get_context as frappe_login_context
    return frappe_login_context(context)
