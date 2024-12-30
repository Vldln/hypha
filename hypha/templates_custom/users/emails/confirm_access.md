{% load i18n wagtailadmin_tags %}{% base_url_setting as base_url %}
{% blocktrans %}Dear {{ user }},{% endblocktrans %}

{% blocktrans %}To confirm access at {{ org_long_name }} Grant Programs & Opportunities, please use the code below (valid for {{ timeout_minutes }} minutes):{% endblocktrans %}

{{ token }}

{% blocktrans %}If you did not request this email, please ignore it.{% endblocktrans %}

{% if org_email %}
{% blocktrans %}For any questions or concerns, feel free to contact us at {{ org_email }}.{% endblocktrans %}
{% endif %}

{% blocktrans %}Kind Regards,
The {{ org_short_name }} Team{% endblocktrans %}

--
{{ org_long_name }}
https://equalit.ie
