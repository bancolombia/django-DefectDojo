{% extends "notifications/mail/base_email.tpl" %}
{% load i18n %}
{% load navigation_tags %}
{% load display_tags %}
{% load static %}

{% url 'view_long_risk_acceptance_details' long_risk_acceptance.id as long_ra_url %}
{% url 'view_product' long_risk_acceptance.product.id as product_url %}

{% block content %}
	{% block header %}
		<h2>{% blocktranslate %}Long-Term Risk Acceptance Notification{% endblocktranslate %}</h2>
	{% endblock %}

	{% block status_section %}
		<br/>
		<table class="proton-table" style="margin: 15px 0;">
			<tr>
				<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
					{% blocktranslate %}Status:{% endblocktranslate %}
				</td>
				<td style="padding: 10px;">
					{{ long_risk_acceptance.risk_status }}
				</td>
			</tr>
			{% if long_risk_acceptance.description %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Description:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.description }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.cause %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Cause:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.cause }}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block dates_section %}
		<br/>
		<h3>{% blocktranslate %}Important Dates{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.created %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Created:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.created|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.expiration_date %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Expiration Date:{% endblocktranslate %}
					</td>
					<td style="padding: 10px; color: #d9534f; font-weight: bold;">
						{{ long_risk_acceptance.expiration_date|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.accepted_date %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Accepted Date:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.accepted_date|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.reviewed_date %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Reviewed Date:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.reviewed_date|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block ownership_section %}
		<br/>
		<h3>{% blocktranslate %}Ownership & Approval{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.owner %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Owner:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.owner.username }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.reviewed_by %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Reviewed By:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.reviewed_by }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.accepted_by %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Accepted By:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.accepted_by.username }}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block product_engagement_section %}
		<br/>
		<h3>{% blocktranslate %}Product & Engagements{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.product %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Product:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						<a href="{{ product_url|full_url }}" style="color: #0066cc;">
							{{ long_risk_acceptance.product.name }}
						</a>
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.engagement_set.all %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold; vertical-align: top;">
						{% blocktranslate %}Engagements:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{% for engagement in long_risk_acceptance.engagement_set.all %}
							<div>• {{ engagement.name }}</div>
						{% endfor %}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block rules_section %}
		{% if long_risk_acceptance.riskacceptanceexclusionrule_set.all %}
			<br/>
			<h3>{% blocktranslate %}Applied Rules{% endblocktranslate %}</h3>
			<table class="proton-table" style="margin: 15px 0;">
				{% for rule in long_risk_acceptance.riskacceptanceexclusionrule_set.all %}
					<tr>
						<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
							{% blocktranslate %}Rule:{% endblocktranslate %}
						</td>
						<td style="padding: 10px;">
							{{ rule.title }} ({{ rule.type_rule }})
						</td>
					</tr>
				{% endfor %}
			</table>
		{% endif %}
	{% endblock %}

	{% block settings_section %}
		<br/>
		<h3>{% blocktranslate %}Expiration Settings{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			<tr>
				<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
					{% blocktranslate %}Reactivate Findings on Expiration:{% endblocktranslate %}
				</td>
				<td style="padding: 10px;">
					{% if long_risk_acceptance.reactivate_expired %}
						<span style="color: green;">✓ {% blocktranslate %}Yes{% endblocktranslate %}</span>
					{% else %}
						<span style="color: red;">✗ {% blocktranslate %}No{% endblocktranslate %}</span>
					{% endif %}
				</td>
			</tr>
		</table>
	{% endblock %}

	{% block action_section %}
		<br/>
		<br/>
		<div style="text-align: center; margin: 30px 0;">
			<p>{% blocktranslate %}For more information, visit the long-term risk acceptance details:{% endblocktranslate %}</p>
			<a href="{{ long_ra_url|full_url }}" class="proton-button" target="_blank" style="display: inline-block; padding: 10px 20px; background-color: #FFC300; color: #333; text-decoration: none; border-radius: 5px; font-weight: bold;">
				{% blocktranslate %}View Risk Acceptance{% endblocktranslate %}
			</a>
		</div>
	{% endblock %}

	{% block footer_section %}
		<br/>
		<br/>
		<hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;">
		<p style="font-size: 12px; color: #666;">
			{% blocktranslate %}This is an automated notification from DefectDojo. Do not reply to this email.{% endblocktranslate %}
		</p>
	{% endblock %}
{% endblock %}
