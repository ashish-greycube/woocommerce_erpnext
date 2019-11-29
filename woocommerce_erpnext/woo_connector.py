# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from woocommerce import API
import frappe
from frappe.utils import cstr,cint
from erpnext.utilities.product import get_price
from erpnext.erpnext_integrations.connectors.woocommerce_connection import (
    verify_request, set_items_in_sales_order, link_customer_and_address)
import json


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
    r = get_connection().get("products/categories?per_page=100").json()
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
                if not categories.get(d.name) or not categories.get(d.name) == cint(d.woocommerce_id_za):
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
        "images": [
            {
                "src": "{}/{}".format(frappe.utils.get_url(), item_doc.image) if item_doc.image else ""
                # "http://demo.woothemes.com/woocommerce/wp-content/uploads/sites/56/2013/06/T_2_front.jpg"
            }
            # ,
            # {
            #     "src": "http://demo.woothemes.com/woocommerce/wp-content/uploads/sites/56/2013/06/T_2_back.jpg"
            # }
        ]
    }


def make_item(item_doc):
    sync_product_categories(item_group=item_doc.item_group)
    product = get_mapped_product(item_doc)
    r = get_connection().post("products", product).json()
    woocommerce_id = r.get("id")
    frappe.db.set_value("Item", item_doc.item_code,
                        "woocommerce_id", woocommerce_id)
    frappe.db.commit()
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
    data = json.loads(payload)
    order(**data)


@frappe.whitelist(allow_guest=True)
def order(*args, **kwargs):
    try:
        _order(*args, **kwargs)
    except Exception:
        error_message = frappe.get_traceback()+"\n\n Request Data: \n" + \
            json.loads(frappe.request.data).__str__()
        frappe.log_error(error_message, "WooCommerce Error")
        raise


def _order(*args, **kwargs):
    woocommerce_settings = frappe.get_doc("Woocommerce Settings")
    if frappe.flags.woocomm_test_order_data:
        order = frappe.flags.woocomm_test_order_data
        event = "created"

    elif frappe.request and frappe.request.data:
        verify_request()
        try:
            order = json.loads(frappe.request.data)
        except ValueError:
            # woocommerce returns 'webhook_id=value' for the first request which is not JSON
            order = frappe.request.data
        event = frappe.get_request_header("X-Wc-Webhook-Event")

    else:
        return "success"

    # event = "created"
    # order = json.loads(payload)

    if event == "created":
        raw_billing_data = order.get("billing")
        customer_name = raw_billing_data.get(
            "first_name") + " " + raw_billing_data.get("last_name")
        link_customer_and_address(raw_billing_data,customer_name)
        create_sales_order(order, woocommerce_settings, customer_name)


def create_sales_order(order, woocommerce_settings, customer_name):
    new_sales_order = frappe.new_doc("Sales Order")
    new_sales_order.customer = customer_name

    new_sales_order.po_no = new_sales_order.woocommerce_id = order.get("id")
    new_sales_order.naming_series = woocommerce_settings.sales_order_series or "SO-WOO-"

    created_date = order.get("date_created").split("T")
    new_sales_order.transaction_date = created_date[0]
    delivery_after = woocommerce_settings.delivery_after_days or 7
    new_sales_order.delivery_date = frappe.utils.add_days(
        created_date[0], delivery_after)

    new_sales_order.company = woocommerce_settings.company

    set_items_in_sales_order(new_sales_order, woocommerce_settings, order)

    for item in new_sales_order.items:
        stock_uom = frappe.db.get_value(
            "Item", {"item_code": item.item_code}, "stock_uom")
        item.update({"uom": stock_uom})

    new_sales_order.flags.ignore_mandatory = True
    new_sales_order.insert()
    new_sales_order.submit()

    frappe.db.commit()


payload = """
{
  "id": 956,
  "parent_id": 0,
  "number": "956",
  "order_key": "wc_order_14AHdr1cc8ESd",
  "created_via": "checkout",
  "version": "3.8.0",
  "status": "on-hold",
  "currency": "USD",
  "date_created": "2019-11-28T14:13:19",
  "date_created_gmt": "2019-11-28T14:13:19",
  "date_modified": "2019-11-28T14:13:20",
  "date_modified_gmt": "2019-11-28T14:13:20",
  "discount_total": "0.00",
  "discount_tax": "0.00",
  "shipping_total": "0.00",
  "shipping_tax": "0.00",
  "cart_tax": "0.84",
  "total": "13.59",
  "total_tax": "0.84",
  "prices_include_tax": false,
  "customer_id": 2,
  "customer_ip_address": "157.32.134.99",
  "customer_user_agent": "Mozilla\\/5.0 (Macintosh; Intel Mac OS X 10_15_1) AppleWebKit\\/537.36 (KHTML, like Gecko) Chrome\\/78.0.3904.108 Safari\\/537.36",
  "customer_note": "",
  "billing": {
    "first_name": "Luz",
    "last_name": "figuereo",
    "company": "",
    "address_1": "Street 1",
    "address_2": "Apt 2",
    "city": "NJ",
    "state": "NJ",
    "postcode": "07001",
    "country": "US",
    "email": "luz@mailhub24.com",
    "phone": "75757575"
  },
  "shipping": {
    "first_name": "",
    "last_name": "",
    "company": "",
    "address_1": "",
    "address_2": "",
    "city": "",
    "state": "",
    "postcode": "",
    "country": ""
  },
  "payment_method": "bacs",
  "payment_method_title": "Direct bank transfer",
  "transaction_id": "",
  "date_paid": null,
  "date_paid_gmt": null,
  "date_completed": null,
  "date_completed_gmt": null,
  "cart_hash": "125b6fc08f7c6f2c96ee1881fa373a7e",
  "meta_data": [
    {
      "id": 11690,
      "key": "is_vat_exempt",
      "value": "no"
    }
  ],
  "line_items": [
    {
      "id": 81,
      "name": "TWO APPLE -50GM-CARTON",
      "product_id": 384,
      "variation_id": 0,
      "quantity": 1,
      "tax_class": "",
      "subtotal": "12.75",
      "subtotal_tax": "0.84",
      "total": "12.75",
      "total_tax": "0.84",
      "taxes": [
        {
          "id": 1,
          "total": "0.84",
          "subtotal": "0.84"
        }
      ],
      "meta_data": [],
      "sku": "TWO APPLE -50GM-CARTON",
      "price": 12.75
    }
  ],
  "tax_lines": [
    {
      "id": 82,
      "rate_code": "US-NJ-NJ TAX-1",
      "rate_id": 1,
      "label": "NJ Tax",
      "compound": false,
      "tax_total": "0.84",
      "shipping_tax_total": "0.00",
      "rate_percent": 6.625,
      "meta_data": []
    }
  ],
  "shipping_lines": [],
  "fee_lines": [],
  "coupon_lines": [],
  "refunds": [],
  "currency_symbol": "$",
  "_links": {
    "self": [
      {
        "href": "https:\\/\\/sf.greycube.in\\/wp-json\\/wc\\/v3\\/orders\\/956"
      }
    ],
    "collection": [
      {
        "href": "https:\\/\\/sf.greycube.in\\/wp-json\\/wc\\/v3\\/orders"
      }
    ],
    "customer": [
      {
        "href": "https:\\/\\/sf.greycube.in\\/wp-json\\/wc\\/v3\\/customers\\/2"
      }
    ]
  }
}

"""

