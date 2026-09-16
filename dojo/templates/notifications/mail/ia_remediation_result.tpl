

{% extends "notifications/mail/base_email.tpl" %}
{% load i18n %}
{% load navigation_tags %}
{% load display_tags %}
{% load static %}
{% url 'view_risk_acceptance' risk_acceptance.engagement.id risk_acceptance.id as risk_acceptance_url %}
{% url 'view_product' risk_acceptance.engagement.product.id as product_url %}
{% url 'view_engagement' risk_acceptance.engagement.id as engagement_url %}
{% block content%}
	{% if ia_remediation_result %}
		<br/>
		<br/>
		<div style="max-width: 700px; border-top: 1px solid #d9d9d9; padding-top: 12px;">
			<b>IA remediation result:</b>
			{% if ia_remediation_result.0 %}
				{% for remediation in ia_remediation_result %}
					<div style="margin-top: 12px; border-bottom: 1px solid #eeeeee; padding-bottom: 10px;">
						<ul style="margin: 0 0 0 20px; padding: 0; max-width: 680px; list-style: disc;">
							{% for key, value in remediation.items %}
								{% if value is None or value == "" %}
								{% elif remediation.status == "ok" and key == "error" %}
								{% elif remediation.status == "ok" and key == "error_message" %}
								{% else %}
									<li style="margin-bottom: 6px; word-break: break-word; overflow-wrap: anywhere; max-width: 660px;">
										<b>{{ key }}:</b>
										<span>{{ value|truncatechars:120 }}</span>
									</li>
								{% endif %}
							{% endfor %}
						</ul>
					</div>
				{% endfor %}
			{% else %}
				<div style="margin-top: 12px;">
					<ul style="margin: 0 0 0 20px; padding: 0; max-width: 680px; list-style: disc;">
						{% for key, value in ia_remediation_result.items %}
							{% if value is None or value == "" %}
							{% elif ia_remediation_result.status == "ok" and key == "error" %}
							{% elif ia_remediation_result.status == "ok" and key == "error_message" %}
							{% else %}
								<li style="margin-bottom: 6px; word-break: break-word; overflow-wrap: anywhere; max-width: 660px;">
									<b>{{ key }}:</b>
									<span>{{ value|truncatechars:120 }}</span>
								</li>
							{% endif %}
						{% endfor %}
					</ul>
				</div>
			{% endif %}
		</div>
	{% endif %}

	{%block acceptance_for_url%}
		<br/>
		<br/>
	{%endblock%}
{%endblock%}









