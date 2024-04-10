## Woocommerce Erpnext

Integration between WooCommerce and ERPNext

# Install:

    # from frappe-bench folder
    # source ./env/bin/activate
    # pip install woocommerce
    # deactivate
    # Setup:

- Copy the existing woo-commerce connector "order" function in custom app
  https://github.com/frappe/erpnext/blob/develop/erpnext/erpnext_integrations/connectors/woocommerce_connection.py#L23

- Edit the code in point 1 to Ignore Item Edit / Creation , it should just link existing items in Sales Order.

- To put sync (custom) button in "Woocommerce Settings", to sync all items.

- On Save of Individual Item, sync Item from ERPNext to Woocommerce ( through the code attached below )

- While saving individual item in ERPNext, check if the item exist in woocommerce, if yes update else create new ( At present in point 4 , it creates new items in woocommerce)

- To check if the direct web link for the item images from erpnext ( e.g. http://demo.erpnext.com/files/two_apple-copiar.jpg(170 kB)
  http://demo.erpnext.com/files/two_apple-copiar.jpg
  ) can be linked to items in woocommerce

### add custom script for Woocommerce Settings doctype. can be exported as fixture

```
frappe.ui.form.on('Woocommerce Settings', {
	refresh(frm) {
    frm.add_custom_button(__("Sync Items to WooCommerce"), () => {
      frappe.call({
        method: "woocommerce_erpnext.woo_connector.sync_all_items"
      });
    });
	}
})
```

#### License

MIT

<hr>

#### Contact Us  

<a href="https://greycube.in"><img src="https://greycube.in/files/greycube_logo09eade.jpg" width="250" height="auto"></a> <br>
1<sup>st</sup> ERPNext [Certified Partner](https://frappe.io/api/method/frappe.utils.print_format.download_pdf?doctype=Certification&name=PARTCRTF00002&format=Partner%20Certificate&no_letterhead=0&letterhead=Blank&settings=%7B%7D&_lang=en#toolbar=0)
<sub> <img src="https://greycube.in/files/certificate.svg" width="20" height="20"> </sub>
& winner of the [Best Partner Award](https://frappe.io/partners/india/greycube-technologies) <sub> <img src="https://greycube.in/files/award.svg" width="25" height="25"> </sub>

<h5>
<sub><img src="https://greycube.in/files/link.svg" width="20" height="auto"> </sub> <a href="https://greycube.in"> greycube.in</a><br>
<sub><img src="https://greycube.in/files/8665305_envelope_email_icon.svg" width="20" height="18"> </sub> <a href="mailto:sales@greycube.in"> 
 sales@greycube.in</a><br>
<sub><img src="https://greycube.in/files/linkedin1.svg" width="20" height="18"> </sub> <a href="https://www.linkedin.com/company/greycube-technologies"> LinkedIn</a><br>
<sub><img src="https://greycube.in/files/blog.svg" width="20" height="18"> </sub><a href="https://greycube.in/blog"> Blogs</a> </h5>
