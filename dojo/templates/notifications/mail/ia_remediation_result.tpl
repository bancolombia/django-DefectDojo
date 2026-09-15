

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
		<b>IA remediation result:</b>
		{% if ia_remediation_result.0 %}
			{% for remediation in ia_remediation_result %}
				<br/>
				<b>Item {{ forloop.counter }}:</b>
				<ul>
					{% for key, value in remediation.items %}
						<li><b>{{ key }}:</b> {{ value|default:"-" }}</li>
					{% endfor %}
				</ul>
			{% endfor %}
		{% else %}
			<ul>
				{% for key, value in ia_remediation_result.items %}
					<li><b>{{ key }}:</b> {{ value|default:"-" }}</li>
				{% endfor %}
			</ul>
		{% endif %}
	{% endif %}
	{% block event %}
		<br/>
		<br/>
		More information on this event can be found here:
		{% blocktranslate trimmed with event_url=url|full_url %}
		<center><a href="{{event_url}}" class="proton-button" target="_blank">Go Risk Acceptance</a></center>
		{% endblocktranslate %}
	{% endblock%}

	{%block acceptance_for_url%}
		<br/>
		<br/>
		{% if enable_acceptance_risk_for_email and permission_keys %}
			If for some reason you cannot login to {{ system_settings.team_name}} you have the option to accept or reject it directly.
			clicking on the following link will automatically accept or reject all findings. use this functionality responsibly.
				{% for permission_key in permission_keys %}
					{% if permission_key.username == user.username%}
						<center><a href="{{permission_key.url_accept}}" class="proton-button-actions-accept button-accept" target="_blank">Accept</a></center>
						<center><a href="{{permission_key.url_reject}}" class="proton-button-actions-reject button-reject" target="_blank">Reject</a></center>
					{% endif %}
				{% endfor %}
		{% endif %}
	{%endblock%}
{%endblock%}









