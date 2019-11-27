# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from woocommerce import API
import frappe
from frappe.utils import cstr
from erpnext.utilities.product import get_price


def handle_response_error(r):
    if r.get("message"):
        frappe.throw(r.get("message"))


def get_connection():
    settings = frappe.get_doc("Woocommerce Settings")
    wcapi = API(
        url=settings.woocommerce_server_url,
        consumer_key=settings.api_consumer_key,
        consumer_secret=settings.api_consumer_secret,
        wp_api=True,
        version="wc/v3"
    )
    return wcapi


@frappe.whitelist()
def sync_all_items():
    # sync erpnext items to WooCommerce product
    for d in frappe.db.get_all("Item"):
        # on_update_item(frappe.get_doc("Item", d))
        frappe.enqueue(on_update_item, doc=frappe.get_doc("Item", d))
        print("updated %s" % d)


def sync_product_categories(item_group=None):
    # sync Erpnext Item Group to WooCommerce Product Category
    # Does not handle nested item group
    r = get_connection().get("products/categories").json()
    categories = {}
    for d in r:
        categories[d["name"]] = d["id"]

    for d in frappe.db.get_list("Item Group", fields=['name', 'woocommerce_id_za']):
        if not item_group or item_group == d.name:
            if not d.woocommerce_id_za:
                if categories.get(d.name):
                    # update erpnext item group with woo id
                    frappe.db.set_value("Item Group", d.name,
                                        "woocommerce_id_za", categories.get(d.name))
                else:
                    # create category in woo
                    product_category_id = make_category(d.name)
                    frappe.db.set_value("Item Group", d.name,
                                        'woocommerce_id_za', product_category_id)
            else:
                if not categories.get(d.name) or not categories.get(d.name) == d.woocommerce_id_za:
                    frappe.throw(
                        "Item group %s (%s)does not match WooCommerce Product Category" % (d.name, d.woocommerce_id_za))

    frappe.db.commit()


def on_update_item(doc, method=None):
    if not doc.woocommerce_id:
        make_item(doc)
    else:
        product = get_mapped_product(doc)
        r = get_connection().put("products/"+doc.woocommerce_id, product)


def get_mapped_product(item_doc):
    wc_product_category_id = frappe.db.get_value(
        "Item Group", item_doc.item_group, "woocommerce_id_za")

    shopping_cart_settings = frappe.get_doc("Shopping Cart Settings")
    item_price = get_price(item_doc.item_code, shopping_cart_settings.price_list,
                           shopping_cart_settings.default_customer_group, shopping_cart_settings.company)

    return {
        "name": item_doc.item_name,
        "type": "simple",
        "regular_price": item_price and cstr(item_price["price_list_rate"]) or "",
        "description": item_doc.description,
        "short_description": item_doc.description,
        "categories": [
            {
                "id": wc_product_category_id
            }
        ],
        # "images": [
        #     {
        #         "src": "http://demo.woothemes.com/woocommerce/wp-content/uploads/sites/56/2013/06/T_2_front.jpg"
        #     },
        #     {
        #         "src": "http://demo.woothemes.com/woocommerce/wp-content/uploads/sites/56/2013/06/T_2_back.jpg"
        #     }
        # ]
    }


def make_item(item_doc):
    sync_product_categories(item_group=item_doc.item_group)
    product = get_mapped_product(item_doc)
    r = get_connection().post("products", product).json()
    woocommerce_id = r.get("id")
    frappe.db.set_value("Item", item_doc.item_code,
                        "woocommerce_id", woocommerce_id)
    return woocommerce_id


def make_category(item_group, image=None):
    data = {
        "name": item_group,
        # "image": {
        #     "src": "http://demo.woothemes.com/woocommerce/wp-content/uploads/sites/56/2013/06/T_2_front.jpg"
        # }
    }
    r = get_connection().post("products/categories", data).json()
    return r.get("id")


def get_category(product_category_id):
    r = get_connection().get("products/categories/" + product_category_id).json()
    return r.get("name")


def test():
    doc = frappe.get_doc("Item", "BANANA CINNAMON-50GM-BOX")
    on_update_item(doc)


@frappe.whitelist(allow_guest=True)
def order(*args, **kwargs):
    try:
        _order(*args, **kwargs)
    except Exception:
        error_message = frappe.get_traceback()+"\n\n Request Data: \n" + \
            json.loads(frappe.request.data).__str__()
        frappe.log_error(error_message, "WooCommerce Error")
        raise


# def _order(*args, **kwargs):
#     woocommerce_settings = frappe.get_doc("Woocommerce Settings")
#     if frappe.flags.woocomm_test_order_data:
#         fd = frappe.flags.woocomm_test_order_data
#         event = "created"

#     elif frappe.request and frappe.request.data:
#         verify_request()
#         fd = json.loads(frappe.request.data)
#         event = frappe.get_request_header("X-Wc-Webhook-Event")

#     else:
#         return "success"

#     if event == "created":
#         def get_mapped_so(data):
#             so = frappe.new_doc("Sales Order")
#             data.get("email")

#             raw_billing_data = fd.get("billing")
#             customer_woo_com_email = raw_billing_data.get("email")

#             if frappe.get_value("Customer", {"woocommerce_email": customer_woo_com_email}):
#                 # Edit
#                 link_customer_and_address(raw_billing_data, 1)
#             else:
#                 # Create
#                 link_customer_and_address(raw_billing_data, 0)

#             items_list = fd.get("line_items")

#             customer_name = raw_billing_data.get(
#                 "first_name") + " " + raw_billing_data.get("last_name")

#             new_sales_order = frappe.new_doc("Sales Order")
#             new_sales_order.customer = customer_name

#             created_date = fd.get("date_created").split("T")
#             new_sales_order.transaction_date = created_date[0]

#             new_sales_order.po_no = fd.get("id")
#             new_sales_order.woocommerce_id = fd.get("id")
#             new_sales_order.naming_series = woocommerce_settings.sales_order_series or "SO-WOO-"

#             placed_order_date = created_date[0]
#             raw_date = datetime.datetime.strptime(
#                 placed_order_date, "%Y-%m-%d")
#             raw_delivery_date = frappe.utils.add_to_date(raw_date, days=7)
#             order_delivery_date_str = raw_delivery_date.strftime('%Y-%m-%d')
#             order_delivery_date = str(order_delivery_date_str)

#             new_sales_order.delivery_date = order_delivery_date
#             default_set_company = frappe.get_doc("Global Defaults")
#             company = raw_billing_data.get(
#                 "company") or default_set_company.default_company
#             found_company = frappe.get_doc("Company", {"name": company})
#             company_abbr = found_company.abbr

#             new_sales_order.company = company

#             for item in items_list:
#                 def get_mapped_item(i):
#                     mapped = frappe.db.get_value("Item", {"woocommerce_id": i.get(
#                         "product_id")}, ['item_code', 'item_name', 'stock_uom', ], as_dict=True)
#                     mapped["uom"] = mapped["stock_uom"]
#                     mapped["description"] = mapped["item_name"]
#                     delete mapped["stock_uom"]

#                 so_item = get_mapped_item(item)
#                 so_item.update(
#                     {
#                         "delivery_date": order_delivery_date,
#                         "ordered_items_tax": item.get("total_tax"),
#                         "warehouse": woocommerce_settings.warehouse or "Stores" + " - " + company_abbr,
#                         "qty": item.get("quantity"),
#                         "rate": item.get("price"),
#                     }
#                 )
#                 new_sales_order.append("items", item)

#                 add_tax_details(new_sales_order, ordered_items_tax,
#                                 "Ordered Item tax", 0)

#             # shipping_details = fd.get("shipping_lines") # used for detailed order
#             shipping_total = fd.get("shipping_total")
#             shipping_tax = fd.get("shipping_tax")

#             add_tax_details(new_sales_order, shipping_tax, "Shipping Tax", 1)
#             add_tax_details(new_sales_order, shipping_total,
#                             "Shipping Total", 1)

#         new_sales_order.submit()

#         frappe.db.commit()
