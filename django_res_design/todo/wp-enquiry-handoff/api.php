<?php

// Get APIs Init
function get_api($url)
{
	$sslverify = (WP_SITE_ENV == 'Local') ? false : true;
	$args = array(
		'sslverify' => $sslverify,
		'headers' => array(
			'Content-Type' => 'application/json',
			'X-API-Key' => X_API_Key
		)
	);

	$api_site = API_SITE_URL;
	$response = wp_remote_get($api_site . $url, $args);
	if (is_wp_error($response)) {
		return $response->get_error_message();;
	}
	$response_data = json_decode($response['body']);

	if ($response_data->status == false) {
		$response_data->message = 'No data found';
		return $response_data;
	}

	return $response_data;
}

// Post APIs Init
function post_api_call($url, $data)
{
	$response_code = "";
	$args = array(
		'body' => $data,
		'sslverify' => false,
		'headers' => array(
			'Content-Type' => 'application/json',
			'X-API-Key' => X_API_Key
		)
	);

	$api_site = API_SITE_URL . $url;
	$response = wp_remote_post($api_site, $args);

	if (!is_wp_error($response) && $response['response']['code'] == 200) {
		$response = wp_remote_retrieve_body($response);
		$response_data = json_decode($response);
	} else {
		if (is_wp_error($response)) {
			$error_message = $response->get_error_message();
		} else {
			$response_code = $response['response']['code'];
		}
		$response_data = $response_code;
	}
	return $response_data;
}

// Post enquiry to the new Villa Collective reservations system (Django).
// Success = HTTP 201 with a {"reference": "E..."} body; retried duplicates
// within the hour replay the same 201, so a resubmit is safe. Deliberately
// NOT using post_api_call: that helper is shared by the payment flows still
// pointed at the legacy system, only accepts HTTP 200, and disables TLS
// verification.
function post_enquiry_to_vc($data)
{
	if (!defined('VC_RES_ENQUIRY_URL') || !defined('VC_RES_API_TOKEN')) {
		error_log('Villa enquiry: VC_RES_ENQUIRY_URL / VC_RES_API_TOKEN not defined in wp-config.php');
		return false;
	}

	$response = wp_remote_post(VC_RES_ENQUIRY_URL, array(
		'body' => $data,
		'timeout' => 30,
		'headers' => array(
			'Content-Type' => 'application/json',
			'Authorization' => 'Token ' . VC_RES_API_TOKEN,
		),
	));

	if (is_wp_error($response)) {
		error_log('Villa enquiry: ' . $response->get_error_message());
		return false;
	}

	$code = wp_remote_retrieve_response_code($response);
	$raw_body = wp_remote_retrieve_body($response);
	$body = json_decode($raw_body);

	if ($code == 201 && !empty($body->reference)) {
		return $body->reference;
	}

	error_log('Villa enquiry: unexpected response ' . $code . ' ' . $raw_body);
	if (function_exists('write_json_to_log')) {
		write_json_to_log(['timestamp' => current_time('mysql'), 'event' => 'vc_enquiry_failed', 'meta' => ['code' => $code, 'body' => $raw_body]]);
	}
	return false;
}

/************************************ Sync Country Start ***************************************/
add_action('rest_api_init', 'wp_sync_country');

function wp_sync_country()
{
	register_rest_route('api/v1', '/WP_Sync_Country', array(
		'methods' => 'POST',
		'callback' => 'wordpress_sync_country'
	));
}

function wordpress_sync_country($request)
{
	$status = false;
	$country_fields = $request->get_params();
	$TrashData = [];
	$BulkData = [];
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	if ($valid != WP_Token) {
		$response['Status'] = $status;
		$response['Message'] = "API Token not matched";
		$response['Data'] = null;
		return json_encode($response);
	}

	// UPDATE COUNTRY API CODE START
	if (isset($country_fields['Countries'])) {
		foreach ($country_fields['Countries'] as $key => $value) {
			$meta_key = 'taxonomy_country_id';
			$term_id = custom_get_term_id($meta_key, $value['CountryId']);
			if ($term_id) {
				$update = wp_update_term($term_id, 'country', array(
					'name' => $value['CountryName'],
					'slug' => sanitize_title($value['CountryName']),
				));
				$c_term_id = 'country_' . $term_id;
				update_field('country_enable', $value['is_Enable'], $c_term_id);
				$BulkData[] = ['PrimaryId' => (int)$value['CountryId'], 'PostId' => (int)$term_id, 'Url' => ""];
			} else {
				$country = get_term_by('name', $value['CountryName'], 'country');
				if ($country == false) {
					$country_term = wp_insert_term($value['CountryName'], 'country');
					$c_term_id = 'country_' . $country_term['term_id'];
					update_field('taxonomy_country_id', $value['CountryId'], $c_term_id);
					update_field('country_enable', $value['is_Enable'], $c_term_id);
					$BulkData[] = ['PrimaryId' => (int)$value['CountryId'], 'PostId' => (int)$country_term['term_id'], 'Url' => ""];
				} else {
					$BulkData[] = ['PrimaryId' => (int)$value['CountryId'], 'PostId' => (int)$country->term_id, 'Url' => ""];
				}
			}
		}
	}
	// UPDATE COUNTRY API CODE OVER

	// DELETE COUNTRY API CODE START
	if (isset($country_fields['DeleteCountries'])) {
		foreach ($country_fields['DeleteCountries'] as $key => $value) {
			$meta_key = 'taxonomy_country_id';
			$term_id = custom_get_term_id($meta_key, $value['CountryId']);
			if ($term_id) {
				$regions = get_terms('country', array(
					'hide_empty' => 0,
					'parent' => $term_id,
				));

				foreach ($regions as $rkey => $rvalue) {
					delete_term_meta($rvalue->term_id, 'taxonomy_country_id');
					delete_term_meta($rvalue->term_id, 'country_enable');
					wp_delete_term($rvalue->term_id, 'country');
				}
				delete_term_meta($term_id, 'taxonomy_country_id');
				delete_term_meta($term_id, 'country_enable');
				wp_delete_term($term_id, 'country');

				$delete = wp_delete_term($term_id, 'country');
				$TrashData[] = ['PrimaryId' => (int)$value['CountryId'], 'PostId' => (int)$term_id, 'Url' => ""];
			}
		}
	}
	// DELETE COUNTRY API CODE OVER

	if ($BulkData || $TrashData)
		$status = true;

	$response['Status'] = $status;
	$response['Message'] = "Country SYNC Done";
	$response['Data'] = null;
	$response['BulkData'] = $BulkData;
	$response['TrashData'] = $TrashData;
	return json_encode($response);
}
/************************************ Sync Country End ***************************************/

/************************************ Sync Region Start ***************************************/
add_action('rest_api_init', 'wp_sync_regions');

function wp_sync_regions()
{
	register_rest_route('api/v1', '/WP_Sync_Regions', array(
		'methods' => 'POST',
		'callback' => 'wordpress_sync_regions'
	));
}

function wordpress_sync_regions($request)
{
	$status = false;
	$BulkData = [];
	$TrashData = [];
	$regions_fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	if ($valid != WP_Token) {
		$response['Status'] = $status;
		$response['Message'] = "API Token not matched";
		$response['Data'] = null;
		return json_encode($response);
	}

	// UPDATE REGIONS API CODE START
	if (isset($regions_fields['Regions'])) {
		foreach ($regions_fields['Regions'] as $key => $value) {
			$meta_key = 'taxonomy_region_id';
			$term_id = custom_get_term_id($meta_key, $value['RegionId']);
			if ($term_id) {
				$update = wp_update_term($term_id, 'country', array(
					'name' => $value['RagionName'],
					'slug' => sanitize_title($value['RagionName']),
				));
				$BulkData[] = ['PrimaryId' => (int)$value['RegionId'], 'PostId' => (int)$term_id, 'Url' => ""];
			} else {
				$regions  = get_term_by('name', $value['RagionName'], 'country');
				if ($regions == false) {
					$meta_key = 'taxonomy_country_id';
					$term_id = custom_get_term_id($meta_key, $value['CountryId']);
					$args = array('parent' => $term_id);
					$region_term = wp_insert_term($value['RagionName'], 'country', $args);
					$r_term_id = 'country_' . $region_term['term_id'];
					update_field('taxonomy_region_id', $value['RegionId'], $r_term_id);
					$BulkData[] = ['PrimaryId' => (int)$value['RegionId'], 'PostId' => (int)$region_term['term_id'], 'Url' => ""];
				} else {
					$BulkData[] = ['PrimaryId' => (int)$value['RegionId'], 'PostId' => (int)$regions->term_id, 'Url' => ""];
				}
			}
		}
	}
	// UPDATE REGIONS API CODE OVER

	// DELETE REGIONS API CODE START
	if (isset($regions_fields['DeleteRegions'])) {
		foreach ($regions_fields['DeleteRegions'] as $key => $value) {
			$meta_key = 'taxonomy_region_id';
			$term_id = custom_get_term_id($meta_key, $value['RegionId']);
			if ($term_id) {
				delete_term_meta($term_id, 'taxonomy_region_id');
				wp_delete_term($term_id, 'country');

				$delete = wp_delete_term($term_id, 'country');
				$TrashData[] = ['PrimaryId' => (int)$value['RegionId'], 'PostId' => (int)$term_id, 'Url' => ""];
			}
		}
	}
	// DELETE REGIONS API CODE OVER

	if ($BulkData || $TrashData)
		$status = true;

	$response['Status'] = $status;
	$response['Message'] = "Region SYNC Done";
	$response['Data'] = null;
	$response['BulkData'] = $BulkData;
	$response['TrashData'] = $TrashData;
	return json_encode($response);
}
/************************************ Sync Region End ***************************************/

/************************************ Sync All Key Feature Start ***************************************/
add_action('rest_api_init', 'sync_key_feature');

function sync_key_feature()
{
	register_rest_route('api/v1', '/Sync_key_feature', array(
		'methods' => 'POST',
		'callback' => 'sync_key_feature_to_wordpress'
	));
}

function sync_key_feature_to_wordpress($req)
{
	$status = false;
	$data = null;
	$BulkData = [];
	$TrashData = [];
	$fields = $req->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = null;
		return json_encode($response);
	}

	// DELETE FEATURE API CODE START	
	if (isset($fields['DeleteFeatures'])) {
		foreach ($fields['DeleteFeatures'] as $key => $value) {
			if ($value['Category']) {
				$feature_category = explode(',', $value['Category']);

				if (in_array("10", $feature_category) || in_array("20", $feature_category) || in_array("30", $feature_category) || in_array("40", $feature_category) || in_array("50", $feature_category) || in_array("60", $feature_category) || in_array("70", $feature_category) || in_array("90", $feature_category)) {
					$meta_key = 'key_features_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						delete_field($meta_key, $term_id);
						delete_term_meta($term_id, 'key_features_id');
						$delete = wp_delete_term($term_id, 'key-feature');
						$TrashData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					}
				}

				if (in_array("50", $feature_category)) {
					$meta_key = 'amenities_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						delete_field($meta_key, $term_id);
						delete_term_meta($term_id, 'amenities_id');
						$delete = wp_delete_term($term_id, 'amenities');
						$TrashData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					}
				}

				if (in_array("70", $feature_category)) {
					$meta_key = 'services_on_request_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						delete_field($meta_key, $term_id);
						delete_term_meta($term_id, 'services_on_request_id');
						$delete = wp_delete_term($term_id, 'services_on_request');
						$TrashData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					}
				}
			} else {
				$meta_key = 'key_features_id';
				$term_id = custom_get_term_id($meta_key, $value['Id']);
				if ($term_id) {
					delete_term_meta($term_id, 'key_features_id');
					$delete = wp_delete_term($term_id, 'key-feature');
					$TrashData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
				}
			}
		}
	}
	// DELETE FEATURE API CODE OVER

	// UPDATE FEATURE API CODE START
	if (isset($fields['Features'])) {

		$existing_taxonomies = [];
		foreach ($fields['Features'] as $key => $value) {
			$existing_taxonomies[] = $value['Name'];
		}

		$post_type = 'villa-detail';
		$taxonomies = get_taxonomies(array(), 'objects');
		foreach ($taxonomies as $taxonomy) {
			$terms = get_terms(array(
				'taxonomy' => $taxonomy->name,
				'hide_empty' => false,
			));

			$term_names = wp_list_pluck($terms, 'name');
			foreach ($existing_taxonomies as $term_name) {
				if (in_array($term_name, $term_names)) {
					$term = get_term_by('name', $term_name, $taxonomy->name);
					if ($term) {
						$args = array(
							'post_type' => $post_type,
							'posts_per_page' => -1,
							'fields' => 'ids',
							'tax_query' => array(
								array(
									'taxonomy' => $taxonomy->name,
									'field' => 'id',
									'terms' => $term->term_id,
								)
							),
						);
						$query = new WP_Query($args);
						if ($query->have_posts()) {
							foreach ($query->posts as $post_id) {
								$removed = wp_remove_object_terms($post_id, $term->term_id, $taxonomy->name);
								if ($removed) {
									//echo "{$term_name} exists in taxonomy '{$taxonomy->name}' and is associated with post type '{$post_type}' - Post ID: {$post_id}  - Term '{$term_name}' has been removed from Post ID {$post_id}.<br>";
								}
							}
						}
						wp_reset_postdata();
					}
				}
			}
		}

		foreach ($fields['Features'] as $key => $value) {
			if ($value['Category']) {
				$feature_category = explode(',', $value['Category']);
				if (in_array("10", $feature_category) || in_array("20", $feature_category) || in_array("30", $feature_category) || in_array("40", $feature_category) || in_array("50", $feature_category) || in_array("60", $feature_category) || in_array("70", $feature_category) || in_array("90", $feature_category)) {
					$meta_key = 'key_features_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						$update = wp_update_term($term_id, 'key-feature', array(
							'name' => $value['Name'],
							'slug' => sanitize_title($value['Name']),
							'description' => $value['Description'],
						));
						$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					} else {
						$key_fea  = get_term_by('name', $value['Name'], 'key-feature');
						if ($key_fea == false) {
							$key_fea_term = wp_insert_term($value['Name'], 'key-feature', ['description' => $value['Description']]);
							if ($key_fea_term['term_id']) {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$key_fea_term['term_id'], 'Url' => ""];
								$k_term_id = 'key-feature_' . $key_fea_term['term_id'];
								update_field('key_features_id', $value['Id'], $k_term_id);
							} else {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => 0, 'Url' => ""];
							}
						} else {
							$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$key_fea->term_id, 'Url' => ""];
						}
					}
				}

				if (in_array("50", $feature_category)) {
					$meta_key = 'amenities_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						$update = wp_update_term($term_id, 'amenities', array(
							'name' => $value['Name'],
							'slug' => sanitize_title($value['Name']),
							'description' => $value['Description'],
						));
						$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					} else {
						$amenities  = get_term_by('name', $value['Name'], 'amenities');
						if ($amenities == false) {
							$amenities_term = wp_insert_term($value['Name'], 'amenities', ['description' => $value['Description']]);
							if ($amenities_term['term_id']) {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$amenities_term['term_id'], 'Url' => ""];
								$a_term_id = 'amenities_' . $amenities_term['term_id'];
								update_field('amenities_id', $value['Id'], $a_term_id);
							} else {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => 0, 'Url' => ""];
							}
						} else {
							$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$amenities->term_id, 'Url' => ""];
						}
					}
				}

				if (in_array("70", $feature_category)) {
					$meta_key = 'services_on_request_id';
					$term_id = custom_get_term_id($meta_key, $value['Id']);
					if ($term_id) {
						$update = wp_update_term($term_id, 'services_on_request', array(
							'name' => $value['Name'],
							'slug' => sanitize_title($value['Name']),
							'description' => $value['Description'],
						));
						$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
					} else {
						$services_on  = get_term_by('name', $value['Name'], 'services_on_request');
						if ($services_on == false) {
							$services_on_term = wp_insert_term($value['Name'], 'services_on_request', ['description' => $value['Description']]);
							if ($services_on_term['term_id']) {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$services_on_term['term_id'], 'Url' => ""];
								$s_term_id = 'services_on_request_' . $services_on_term['term_id'];
								update_field('services_on_request_id', $value['Id'], $s_term_id);
							} else {
								$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => 0, 'Url' => ""];
							}
						} else {
							$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$services_on->term_id, 'Url' => ""];
						}
					}
				}
			} else {
				$meta_key = 'key_features_id';
				$term_id = custom_get_term_id($meta_key, $value['Id']);
				if ($term_id) {
					$update = wp_update_term($term_id, 'key-feature', array(
						'name' => $value['Name'],
						'slug' => sanitize_title($value['Name']),
						'description' => 'Default',
					));
					$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
				} else {
					$key_fea  = get_term_by('name', $value['Name'], 'key-feature');
					if ($key_fea == false) {
						$key_fea_term = wp_insert_term($value['Name'], 'key-feature', ['description' => 'Default']);
						if ($key_fea_term['term_id']) {
							$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$key_fea_term['term_id'], 'Url' => ""];
							$k_term_id = 'key-feature_' . $key_fea_term['term_id'];
							update_field('key_features_id', $value['Id'], $k_term_id);
						} else {
							$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => 0, 'Url' => ""];
						}
					} else {
						$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$key_fea->term_id, 'Url' => ""];
					}
				}
			}
		}
	}
	// UPDATE FEATURE API CODE OVER

	if ($BulkData || $TrashData)
		$status = true;

	$response['Status'] = $status;
	$response['Message'] = 'Feature SYNC Done';
	$response['Data'] = $data;
	$response['BulkData'] = $BulkData;
	$response['TrashData'] = $TrashData;
	return json_encode($response);
}
/************************************ Sync All Key Feature End ***************************************/

/************************************ Sync Collections Start ***************************************/
add_action('rest_api_init', 'wp_sync_collections');

function wp_sync_collections()
{
	register_rest_route('api/v1', '/WP_Sync_Collections', array(
		'methods' => 'POST',
		'callback' => 'wordpress_sync_collections'
	));
}

function wordpress_sync_collections($request)
{
	$status = false;
	$BulkData = [];
	$TrashData = [];
	$fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	if ($valid != WP_Token) {
		$response['Status'] = $status;
		$response['Message'] = "API Token not matched";
		$response['Data'] = null;
		return json_encode($response);
	}

	// UPDATE COLLECTIONS API CODE START
	if (isset($fields['Collections'])) {
		foreach ($fields['Collections'] as $key => $value) {
			$meta_key = 'collation_id';
			$term_id = custom_get_term_id($meta_key, $value['Id']);

			if ($term_id) {
				$update = wp_update_term($term_id, 'collections', array(
					'name' => $value['Text'],
					'slug' => sanitize_title($value['Text']),
				));

				$c_term_id = 'collections_' . $term_id;
				update_field('collections_enable', $value['is_Enable'], $c_term_id);
				$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
			} else {
				$collections  = get_term_by('name', $value['Text'], 'collections');
				if ($collections == false) {
					$collections_term = wp_insert_term($value['Text'], 'collections');
					$c_term_id = 'collections_' . $collections_term['term_id'];
					update_field('collation_id', $value['Id'], $c_term_id);
					update_field('collections_enable', $value['is_Enable'], $c_term_id);
					$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$collections_term['term_id'], 'Url' => ""];
				} else {
					$BulkData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$collections->term_id, 'Url' => ""];
				}
			}
		}
	}
	// UPDATE COLLECTIONS API CODE OVER

	// DELETE COLLECTIONS API CODE START
	if (isset($fields['DeleteCollections'])) {
		foreach ($fields['DeleteCollections'] as $key => $value) {
			$meta_key = 'collation_id';
			$term_id = custom_get_term_id($meta_key, $value['Id']);
			if ($term_id) {
				delete_term_meta($term_id, 'collation_id');
				delete_term_meta($term_id, 'collections_enable');
				wp_delete_term($term_id, 'collections');

				$delete = wp_delete_term($term_id, 'collections');
				$TrashData[] = ['PrimaryId' => (int)$value['Id'], 'PostId' => (int)$term_id, 'Url' => ""];
			}
		}
	}
	// DELETE COLLECTIONS API CODE OVER

	if ($BulkData || $TrashData)
		$status = true;

	$response['Status'] = $status;
	$response['Message'] = "Collation SYNC Done";
	$response['Data'] = null;
	$response['BulkData'] = $BulkData;
	$response['TrashData'] = $TrashData;
	return json_encode($response);
}
/************************************ Sync Collections End ***************************************/

/************************************ Sync Villa Start ***************************************/
add_action('rest_api_init', 'wp_sync_villa');

function wp_sync_villa()
{
	register_rest_route('api/v1', '/WP_Sync_Villa', array(
		'methods' => 'POST',
		'callback' => 'wordpress_sync_villa'
	));
}

function wordpress_sync_villa($request)
{
	$status = false;
	$sync_error = [];
	$is_delete_field = false;
	$is_create_field = false;
	$is_update_field = false;


	$fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = null;
		return json_encode($response);
	}

	if ($fields['PropertyId'] == '' || $fields['PropertyId'] == 0) {
		$response['Status'] = $status;
		$response['Message'] = "Property Id is 0 or blank";
		$response['Data'] = null;
		return json_encode($response);
	}

	/* Check and Set Villa Status */
	$check_post_type = array('publish', 'draft', 'pending', 'future', 'private', 'inherit', 'trash', 'live_offline', 'archive');
	if (isset($fields['VillaStatus'])) {

		// Please change villa status as per Date: 03-04-2025
		if ($fields['VillaStatus'] == 'live_online') {
			$set_post_status = 'publish';
		} else if ($fields['VillaStatus'] == 'live_offline') {
			$set_post_status = 'publish';
		} else if ($fields['VillaStatus'] == 'pending') {
			$set_post_status = 'draft';
		} else if ($fields['VillaStatus'] == 'archive') {
			$set_post_status = 'draft';
		}
	}

	if (isset($fields['Action']) && $fields['Action'] == 'CREATE_FIELD') {
		$is_create_field = true;
	}

	// added after RES2
	if (isset($fields['Action']) && $fields['Action'] == 'INSERT_FIELD') {
		$is_create_field = true;
	}

	if (isset($fields['Action']) && $fields['Action'] == 'DELETE_FIELD') {
		$is_delete_field = true;
	}

	if (isset($fields['Action']) && $fields['Action'] == 'UPDATE_FIELD') {
		$is_update_field = true;
	}

	if (isset($fields['Action']) && $fields['Action'] == 'DELETE') {
		$args = array(
			'posts_per_page' => 1,
			'post_type' => 'villa-detail',
			'post_status' => $check_post_type,
			'meta_query' => array(
				array(
					'key' => 'propertyid',
					'value' => $fields['PropertyId']
				)
			),
		);
		$posts = get_posts($args);

		if (empty($posts)) {
			$response['Status'] = $status;
			$response['Message'] = "Villa doesn't exsist with this propertid";
			$response['Data'] = null;
			return json_encode($response);
		}
		$delete_id = $posts[0]->ID;
		$delete_post = wp_delete_post($delete_id);

		if (!empty($delete_post)) {
			$status = true;
			$message = "Villa Deleted Successfully";
		} else {
			$message = "Villa Not delete Please check";
		}
		$response['Status'] = $status;
		$response['Message'] = $message;
		$response['Data'] = ['PrimaryId' => $fields['PropertyId'], 'PostId' => 0, 'Url' => ''];
		$response['BulkData'] = null;
		return json_encode($response);
	}

	$is_update = false;
	if (isset($fields['Action']) && $fields['Action'] == 'UPDATE') {
		$is_update = true;
		$property_id = $fields['PropertyId'];

		$args = array(
			'posts_per_page' => 1,
			'post_type' => 'villa-detail',
			'post_status' => $check_post_type,
			'meta_query' => array(
				array(
					'key' => 'propertyid',
					'value' => $property_id
				)
			),
		);

		$update_posts = get_posts($args);
		$update_id = $update_posts[0]->ID;

		$update_post = array(
			'ID' => $update_id,
			'post_type' => 'villa-detail',
			'post_status' => $set_post_status,
			'post_title'   => $fields['Name'],
			'post_name'   => sanitize_title($fields['Name']),
		);

		wp_update_post($update_post);
	}

	$args = array(
		'posts_per_page' => 1,
		'post_type' => 'villa-detail',
		'post_status'   => $check_post_type,
		'meta_query' => array(
			array(
				'key' => 'propertyid',
				'value' => $fields['PropertyId'],
				'compare' => '='
			)
		),
	);
	$posts = get_posts($args);

	if (empty($posts)) {
		$post = array(
			'post_title'    => wp_strip_all_tags($fields['Name']),
			'post_status'   => $set_post_status,
			'post_type'     => 'villa-detail'
		);
		$postId = wp_insert_post($post);
		update_field(strtolower('PropertyId'), $fields['PropertyId'], $postId);
	} else {
		$postId = $posts[0]->ID;
	}

	unset($fields['Name']);

	$key_feature_count = 0;
	$key_feature_count_sp = 0;
	foreach ($fields as $key => $value) {
		if ($postId) {

			if (is_array($value) && empty($value)) {
				update_field(strtolower($key), '', $postId);
				continue;
			}

			// Common logic for handling multiple image fields
			$image_fields = ['Galaries', 'InteriorImages', 'ExteriorImages', 'GridImages'];
			if (in_array($key, $image_fields)) {
				$attachment_ids = array_map(function ($sub_value) use ($fields) {
					return get_or_upload_image($sub_value, $fields['PropertyId']);
				}, $value);
				update_field(strtolower($key), $attachment_ids, $postId);
			} elseif ($key == 'PropertyImage') {
				// Special handling for PropertyImage (set as post thumbnail)
				$attachment_id = get_or_upload_image($value, $fields['PropertyId']);
				set_post_thumbnail($postId, $attachment_id);
			} else if ($key == 'IndoorFeatures' || $key == 'OutdoorFeatures') {
				$term_ids = [];
				$key_term_ids = [];

				foreach ($value as $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$term = get_term_by('name', $sub_value['Name'], 'key-feature');
						if ($term && !is_wp_error($term)) {
							$term_ids[] = $term->term_id;
							$key_term_ids[] = $term->term_id;
						}
					}
				}
				if (!empty($term_ids)) {
					$taxonomy = 'key-feature';

					if ($key_feature_count != 0) {
						$existing_terms = wp_get_post_terms($postId, $taxonomy, ['fields' => 'ids']);
						$term_ids = array_unique(array_merge($existing_terms, $term_ids));
					}
					$key_feature_count++;
					wp_set_post_terms($postId, $term_ids, $taxonomy);
				}

				if (!empty($key_term_ids)) {
					update_field(strtolower($key), $key_term_ids, $postId);
				}
			} else if ($key == 'IndoorFeaturesData') {
				$IndoorFeatures  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$IndoorFeatures[$sub_key]['name'] = $sub_value['Name'];
						$IndoorFeatures[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $IndoorFeatures, $postId);
			} else if ($key == 'OutdoorFeaturesData') {
				$OutdoorFeatures  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$OutdoorFeatures[$sub_key]['name'] = $sub_value['Name'];
						$OutdoorFeatures[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $OutdoorFeatures, $postId);
			} else if ($key == 'IncludedFeatures') {
				$IncludedFeatures  = [];
				$term_ids = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$meta_key = 'amenities_id';
						$term = get_term_by('name', $sub_value['Name'], 'amenities');
						$term_id = $term->term_id;
						$taxonomy =  'amenities';
						if ($term_id) {
							$term_ids[] = $term_id;
						}
					}
				}
				wp_set_post_terms($postId, $term_ids, $taxonomy);
				update_field(strtolower($key), $term_ids, $postId);
			} else if ($key == 'Collections') {
				$term_ids = [];
				$taxonomy =  'collections';
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$term = get_term_by('name', $sub_value['Name'], 'collections');
						$term_id = $term->term_id;
						if ($term_id) {
							$term_ids[] = $term_id;
						}
					}
				}
				wp_set_post_terms($postId, $term_ids, $taxonomy);
				update_field(strtolower($key), $term_ids, $postId);
			} else if ($key == 'LivingSpaces') {
				$LivingSpaces  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$LivingSpaces[$sub_key]['space_name'] = $sub_value['Name'];
						$LivingSpaces[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $LivingSpaces, $postId);
			} else if ($key == 'Outdoors') {
				$Outdoors  = [];
				foreach ($value as $sub_key => $sub_value) {
					//if(isset($sub_value['IsActive']) && $sub_value['IsActive']){
					$Outdoors[$sub_key]['outdoors_name'] = $sub_value;
					//}
				}
				update_field(strtolower($key), $Outdoors, $postId);
			} else if ($key == 'ServiceIncluded') {
				$ServiceIncluded  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$ServiceIncluded[$sub_key]['service_name'] = $sub_value['Name'];
						$ServiceIncluded[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $ServiceIncluded, $postId);
			} else if ($key == 'ServiceOnRequest') {
				$ServiceOnRequest  = [];
				$term_ids = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$ServiceOnRequest[$sub_key]['service_request_name'] = $sub_value['Name'];
						$ServiceOnRequest[$sub_key]['description'] = $sub_value['Description'];
						$term = get_term_by('name', $sub_value['Name'], 'services_on_request');
						$term_id = $term->term_id;
						$taxonomy =  'services_on_request';
						if ($term_id) {
							$term_ids[] = $term_id;
						}
					}
				}
				wp_set_post_terms($postId, $term_ids, $taxonomy);
				update_field(strtolower($key), $ServiceOnRequest, $postId);
			} else if ($key == 'OtherInformation') {
				$OtherInformation  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$OtherInformation[$sub_key]['other_info_name'] = $sub_value['Name'];
						$OtherInformation[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $OtherInformation, $postId);
			} else if ($key == 'RentToGatherData') {
				$postmeta_ids  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$meta_key = 'propertyid';
						$postmeta_ids[] = custom_get_post_id($meta_key, $sub_value['PropertyId']);
					}
				}
				update_field(strtolower($key), $postmeta_ids, $postId);
			} else if ($key == 'PupularProperties') {
				$postmeta_ids  = [];
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$meta_key = 'propertyid';
						$postmeta_ids[] = custom_get_post_id($meta_key, $sub_value['PropertyId']);
					}
				}
				update_field(strtolower($key), $postmeta_ids, $postId);
			} else if ($key == 'RoomDetails') {
				$RoomDetails  = [];
				// if ( $is_create_field ||  $is_update_field || $is_delete_field ) {
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$RoomDetails[$sub_key]['placement'] = $sub_value['Placement'];
						$RoomDetails[$sub_key]['roomdetailid'] = $sub_value['RoomDetailId'];
						$RoomDetails[$sub_key]['name'] = $sub_value['Name'];
						$RoomDetails[$sub_key]['description'] = $sub_value['Description'];
					}
				}
				update_field(strtolower($key), $RoomDetails, $postId);
				// }
			} else if ($key == 'NearByData') {
				$NearByData  = [];
				// if ( $is_create_field ||  $is_update_field || $is_delete_field ) {
				foreach ($value as $sub_key => $sub_value) {
					if (isset($sub_value['IsActive']) && $sub_value['IsActive']) {
						$NearByData[$sub_key]['id'] = $sub_value['Id'];
						$NearByData[$sub_key]['categorytype'] = $sub_value['CategoryType'];
						$NearByData[$sub_key]['name'] = $sub_value['Name'];
						$NearByData[$sub_key]['distance'] = $sub_value['Distance'];
						$NearByData[$sub_key]['description'] = $sub_value['Description'];
						$NearByData[$sub_key]['bywalk'] = $sub_value['ByWalk'];
						$NearByData[$sub_key]['bydrive'] = $sub_value['ByDrive'];
						$NearByData[$sub_key]['byboat'] = $sub_value['ByBoat'];
					}
				}
				update_field(strtolower($key), $NearByData, $postId);
				// }
			} else if ($key == 'CountryId') {
				$meta_key = 'taxonomy_country_id';
				$term_id = custom_get_term_id($meta_key, $value);
				$taxonomy =  'country';
				wp_set_post_terms($postId, $term_id, $taxonomy);
				update_field(strtolower($key), $value, $postId);
			} else if ($key == 'StateId') {
				$term_ids = [];
				$country = get_the_terms($postId, 'country');

				$term_ids[] = $country[0]->term_id;
				$meta_key = 'taxonomy_region_id';
				$term_ids[] = custom_get_term_id($meta_key, $value);
				$taxonomy =  'country';
				wp_set_post_terms($postId, $term_ids, $taxonomy);
				update_field(strtolower($key), $value, $postId);
			} else if ($key == 'KeyFeatures') {
				$term_ids = [];
				$key_term_ids = [];

				foreach ($value as $sub_value) {
					$term = get_term_by('name', $sub_value['Name'], 'key-feature');
					if ($term && !is_wp_error($term)) {
						$term_ids[] = $term->term_id;
						$key_term_ids[] = $term->term_id;
					}
				}
				if (!empty($term_ids)) {
					$taxonomy = 'key-feature';

					if ($key_feature_count_sp != 0) {
						$existing_terms = wp_get_post_terms($postId, $taxonomy, ['fields' => 'ids']);
						$term_ids = array_unique(array_merge($existing_terms, $term_ids));
					}
					$key_feature_count_sp++;
					wp_set_post_terms($postId, $term_ids, $taxonomy);
				}

				if (!empty($key_term_ids)) {
					update_field(strtolower($key), $key_term_ids, $postId);
				}
			} else {
				$sync_all_other_fields = update_field(strtolower($key), $value, $postId);
			}
		}
	}

	$status = true;

	$response['Status'] = $status;
	$response['Message'] = "Villa SYNC Done";
	$response['Data'] = ['PrimaryId' => $fields['PropertyId'], 'PostId' => $postId, 'Url' => get_the_permalink($postId)];
	$response['BulkData'] = null;

	return json_encode($response);
}
/************************************ Sync Villa End ***************************************/

/************************************ Villa upload image Start ***************************************/
/*
add_action('rest_api_init', 'create_upload_villa_endpoint');

function create_upload_villa_endpoint()
{
	register_rest_route(
		'api/v1',
		'/villa_id/(?P<id>\d+)',
		array(
			'methods' => 'POST',
			'callback' => 'upload_image_to_media',
		)
	);
}

function upload_image_to_media(WP_REST_Request $data)
{
	$status = false;
	$response['status'] = $status;
	$response['message'] = 'Villa id is blank OR 0';
	$response['data'] = "";

	$villa_id = $data['id'];
	$auth = apache_request_headers();

	$valid = $auth['Authorization'];

	if ($villa_id == 0 || $villa_id == '') {
		return json_encode($response);
	}

	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = 'Auth Token not match';
		$response['data'] = "";
		return json_encode($response);
	}

	$villa = get_api("Properties/GetAllPropertyImages?propertyId=" . $villa_id);
	$base_url = $villa->Base_url;
	$villa_details = $villa->data;

	if (empty($villa_details)) {
		$response['status'] = $status;
		$response['message'] = 'Villa is not exist or blank';
		$response['data'] = "";
		return json_encode($response);
	}

	foreach ($villa_details->PropertyImages as $image_detalis) {
		
		$upload_dir = wp_upload_dir();
		$file = $upload_dir['basedir'] . '/villa-image/' . $villa_id . '/' . $image_detalis;

		if (!file_exists($file)) {
			$image_url = $base_url . $image_detalis; //This is the sanitized image url.
			$image = pathinfo($image_url); //Extracting information into array.
			$image_name = $image['basename'];

			if (WP_SITE_ENV == 'Local') {
				$arrContextOptions = array(
					"ssl" => array(
						"verify_peer" => false,
						"verify_peer_name" => false,
					),
				);
				$image_data = file_get_contents($image_url, false, stream_context_create($arrContextOptions));
			} else {
				$image_data = file_get_contents($image_url);
			}

			$unique_file_name = wp_unique_filename($upload_dir['path'], $image_name);
			$filename = basename($unique_file_name);
			if (!empty($image_data)) {
				if ($image != '') {
					wp_mkdir_p($upload_dir['basedir'] . '/villa-image/' . $villa_id);
					$file = $upload_dir['basedir'] . '/villa-image/' . $villa_id . '/' . $filename;
					file_put_contents($file, $image_data);
					$wp_filetype = wp_check_filetype($filename, null);

					// Set attachment data
					$attachment = array(
						'post_mime_type' => $wp_filetype['type'],
						'post_title' => sanitize_file_name($filename),
						'post_content' => '',
						'post_status' => 'inherit',
					);

					// Create the attachment
					$attach_id = wp_insert_attachment($attachment, $file);
					update_post_meta($attach_id, 'villa_id', $villa_id);

					// Include image.php
					require_once ABSPATH . 'wp-admin/includes/image.php';

					// Define attachment metadata
					$attach_data = wp_generate_attachment_metadata($attach_id, $file);

					// Assign metadata to attachment
					wp_update_attachment_metadata($attach_id, $attach_data);
				}
			}
		}
	}

	$status = true;
	$response['status'] = $status;
	$response['message'] = 'Image SYNC Done';
	$response['data'] = "";

	return json_encode($response);
}
*/
/************************************ Villa upload image End ***************************************/

/************************************ Delete All Images Start ***************************************/
add_action('rest_api_init', 'delete_image_api');

function delete_image_api()
{
	register_rest_route(
		'api/v1/delete/',
		'/villa_id/(?P<id>\d+)',
		array(
			'methods' => 'POST',
			'callback' => 'delete_image_media',
		)
	);
}

function delete_image_media(WP_REST_Request $data)
{
	$status = false;
	$response['status'] = $status;
	$response['message'] = "";
	$response['data'] = "";

	$villa_id = $data['id'];
	$auth = apache_request_headers();

	$valid = $auth['Authorization'];

	if ($villa_id == 0 || $villa_id == '') {
		return json_encode($response);
	}

	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = "";
		return json_encode($response);
	}

	$villa = get_api("Properties/GetAllPropertyImages?propertyId=" . $villa_id);
	$base_url = $villa->Base_url;
	$villa_details = $villa->data;

	if (empty($villa_details)) {
		$status = true;
		$response['status'] = $status;
		$response['message'] = "Villa is not exist or blank";
		$response['data'] = "";
		return json_encode($response);
	}

	$uploads = wp_upload_dir();
	$upload_path = $uploads['baseurl'] . '/villa-image/' . $villa_id . '/';
	foreach ($villa_details->PropertyImages as $image_value) {
		$attachmentid = attachment_url_to_postid($upload_path . $image_value);
		if ($attachmentid) {
			wp_delete_attachment($attachmentid);
		}
	}

	$status = true;
	$response['status'] = $status;
	$response['message'] = "All Images Are Deleted";

	return json_encode($response);
}
/************************************ Delete All Images End ***************************************/

/************************************ Delete Image By Name Start ***************************************/
add_action('rest_api_init', function () {
	register_rest_route('api/v1/delete/', '/image_delete/(?P<id>\d+)', array(
		'methods' => 'POST',
		'callback' => 'delete_image_media_by_name',
	));
});

function delete_image_media_by_name(WP_REST_Request $data)
{
	$status = false;
	$response['status'] = $status;
	$response['message'] = "";
	$response['data'] = "";

	$auth = apache_request_headers();

	$valid = $auth['Authorization'];
	$villa_id = $data['id'];

	if ($villa_id == 0 || $villa_id == '') {
		$response['status'] = $status;
		$response['message'] = "Villa id is not valid";
		$response['data'] = "";
		return json_encode($response);
	}

	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = "";
		return json_encode($response);
	}

	$images = $data['image_name'];
	if (empty($images)) {
		$response['status'] = $status;
		$response['message'] = "Please add image name";
		$response['data'] = "";
		return json_encode($response);
	}

	$uploads = wp_upload_dir();
	$villa_id = $data['id'];
	$upload_path = $uploads['baseurl'] . '/villa-image/' . $villa_id . '/';

	$attachmentid = attachment_url_to_postid($upload_path . $images);
	if ($attachmentid) {
		wp_delete_attachment($attachmentid);
	}

	$status = true;
	$response['status'] = $status;
	$response['message'] = "Image Deleted";

	return json_encode($response);
}
/************************************ Delete Image By Name End ***************************************/

/************************************ Villa Sync Cron Start ***************************************/
/*
add_action('villa_custom_cron', 'villa_custom_cron_func');

function villa_custom_cron_func()
{
	$villaimage = get_api("Properties/GetAllPropertyImages");
	foreach ($villaimage->data as $key => $value) {
		$status = false;
		$villa_id = $value->PropertyId;

		if ($villa_id == 0 || $villa_id == '') {
			$response['status'] = $status;
			return json_encode($response);
		}

		$villa = get_api("Properties/GetAllPropertyImages?propertyId=" . $villa_id);
		$base_url = $villa->Base_url;
		$villa_details = $villa->data;


		if (empty($villa_details)) {
			return $status;
		}
					
		$image_meta_detail = array();
		foreach ($villa_details->PropertyImages as $image_detalis) {
			$upload_dir = wp_upload_dir();
			$file = $upload_dir['basedir'] . '/villa-image/' . $villa_id . '/' . $image_detalis;
			if (!file_exists($file)) {
				$image_url = $base_url . $image_detalis; //This is the sanitized image url.
				$image = pathinfo($image_url); //Extracting information into array.
				$image_name = $image['basename'];
				$image_data = file_get_contents($image_url);
				$unique_file_name = wp_unique_filename($upload_dir['path'], $image_name);
				$filename = basename($unique_file_name);

				if (!empty($image_data)) {
					$image_meta_detail[] = $unique_file_name;
					wp_mkdir_p($upload_dir['basedir'] . '/villa-image/' . $villa_id);
					$file = $upload_dir['basedir'] . '/villa-image/' . $villa_id . '/' . $filename;
					file_put_contents($file, $image_data);
					$wp_filetype = wp_check_filetype($filename, null);

					// Set attachment data
					$attachment = array(
						'post_mime_type' => $wp_filetype['type'],
						'post_title' => sanitize_file_name($filename),
						'post_content' => '',
						'post_status' => 'inherit',
					);

					// Create the attachment
					$attach_id = wp_insert_attachment($attachment, $file);
					update_post_meta($attach_id, 'villa_id', $villa_id);

					require_once ABSPATH . 'wp-admin/includes/image.php';

					// Define attachment metadata
					$attach_data = wp_generate_attachment_metadata($attach_id, $file);

					// Assign metadata to attachment
					wp_update_attachment_metadata($attach_id, $attach_data);
				}
			}

			if (!empty($image_meta_detail)) {
				$image_info = json_encode($image_meta_detail);
				update_post_meta($attach_id, 'uplode_villa_id_' . $villa_id, $image_info);
			}
		}
		
		$status = true;
		$response['status'] = $status;
	}
	return json_encode($response);
}
*/
/************************************ Villa Sync Cron End ***************************************/

/************************************ Booking Start ***************************************/
add_action('rest_api_init', 'wp_import_booking');

function wp_import_booking()
{
	register_rest_route('api/v1', '/Import_Booking', array(
		'methods' => 'POST',
		'callback' => 'wordpress_import_booking'
	));
}

function wordpress_import_booking($request)
{
	// Init
	$status = false;
	$fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	// Validations
	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = null;
		return json_encode($response);
	}
	if (!isset($fields['BookingId'])) {
		$response['Status'] = $status;
		$response['Message'] = "BookingReference is blank";
		$response['Data'] = null;
		return json_encode($response);
	}

	// Import Start
	$check_post_type = array('publish', 'draft', 'pending', 'future', 'private', 'inherit', 'trash');
	$set_post_status = 'publish';
	$args = array(
		'posts_per_page' => 1,
		'post_type' => 'booking',
		'post_status'   => $check_post_type,
		'meta_query' => array(
			array(
				'key' => 'BookingId',
				'value' => $fields['BookingId'],
				'compare' => '='
			)
		),
	);
	$posts = get_posts($args);

	if (empty($posts)) {

		// generate unique post name from generate unique string function
		$generate_booking_param = generateUniqueString();

		$post = array(
			'post_title'    => $generate_booking_param,
			'post_status'   => $set_post_status,
			'post_type'     => 'booking'
		);

		// insert the new booking
		$postId = wp_insert_post($post);
		$postName = $generate_booking_param;
		$message = "Booking Added";

		// update ACF value
		update_field(strtolower('BookingId'), $fields['BookingId'], $postId);
	} else {
		// get the existing bookin from 'BookingId'
		$postId = $posts[0]->ID;
		$postName = $posts[0]->post_title;
		$message = "Booking Updated";
	}

	if ($postId) {
		$status = true;
		foreach ($fields as $key => $value) {
			$update_this_key = strtolower($key);

			if ($key == 'PropertyIds') {
				$PropertyIds  = [];
				foreach ($value as $sub_key => $sub_value) {
					$meta_key = 'propertyid';
					$PropertyIds[] = custom_get_post_id($meta_key, $sub_value);
				}
				update_field($update_this_key, $PropertyIds, $postId);
			} else if ($key == 'PersonalInfo') {
				$personal_info[] = [
					'title' => $value['Title'],
					'firstname' => $value['FirstName'],
					'lastname' => $value['LastName'],
					'streetaddress' => $value['StreetAddress'],
					'citytown' => $value['CityTown'],
					'postalcode' => $value['PostalCode'],
					'country' => [
						[
							'countryid' => (int) $value['Country']['CountryId'],
							'countryname' => $value['Country']['CountryName'],
							'countrycode' => $value['Country']['CountryCode'],
						]
					],
					'emailaddress' => $value['EmailAddress'],
					'phonenumber' => $value['PhoneNumber'],
					'otherphone' => $value['OtherPhone'],
				];
				update_field($update_this_key, $personal_info, $postId);
			} else if ($key == 'Currency') {
				$currency_info[] = [
					'id' => (int) $value['Id'],
					'name' => $value['Name'],
					'code' => $value['Code'],
					'symbol' => $value['Symbol'],
				];
				update_field($update_this_key, $currency_info, $postId);
			} else if ($key == 'PaymentSchedule') {
				$payment_schedule[] = [
					'bookingvalue' => (float) $value['BookingValue'],
					'totalamount' => (float) $value['TotalAmount'],
					'bookingextras' => isset($value['BookingExtras']) && is_array($value['BookingExtras']) ? array_map(function ($extra) {
						return [
							'description' => $extra['Description'],
							'amount' => (float) $extra['Amount'],
						];
					}, $value['BookingExtras']) : []
				];
				update_field($update_this_key, $payment_schedule, $postId);
			} else if ($key == 'PaymentDuesDates') {
				$PaymentDuesDates  = [];
				foreach ($value as $sub_key => $sub_value) {
					$PaymentDuesDates[$sub_key]['id'] = $sub_value['Id'] ?? "";
					$PaymentDuesDates[$sub_key]['description'] = $sub_value['Description'];
					$PaymentDuesDates[$sub_key]['amount'] = (float) $sub_value['Amount'];
					$PaymentDuesDates[$sub_key]['date'] = $sub_value['Date'];
					$PaymentDuesDates[$sub_key]['ispayment'] = $sub_value['IsPayment'] ?? false;
				}
				update_field($update_this_key, $PaymentDuesDates, $postId);
			} else {
				$update_all_other_fields = update_field($update_this_key, $value, $postId);
			}
		}
	}
	// Import End

	// Retrurn Response
	$response['Status'] = $status;
	$response['Message'] = $message;
	$response['Data'] = ['BookingId' => $fields['BookingId'], 'BookingReference' => $fields['BookingReference'], 'PostId' => $postId, 'PostName' => $postName, 'Url' => get_the_permalink($postId)];

	return json_encode($response);
}
/************************************ Booking End ***************************************/

add_action('rest_api_init', 'wp_payment_dues_dates');

function wp_payment_dues_dates()
{
	register_rest_route('api/v1', '/PaymentDuesDates', array(
		'methods' => 'POST',
		'callback' => 'wordpress_payment_dues_dates'
	));
}

function wordpress_payment_dues_dates($request)
{
	// Init
	$status = false;
	$fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	// Validations
	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = null;
		return json_encode($response);
	}
	if (!isset($fields['BookingId'])) {
		$response['Status'] = $status;
		$response['Message'] = "BookingReference is blank";
		$response['Data'] = null;
		return json_encode($response);
	}

	// Import Start
	$check_post_type = array('publish', 'draft', 'pending', 'future', 'private', 'inherit', 'trash');
	$set_post_status = 'publish';
	$args = array(
		'posts_per_page' => 1,
		'post_type' => 'booking',
		'post_status'   => $check_post_type,
		'meta_query' => array(
			array(
				'key' => 'BookingId',
				'value' => $fields['BookingId'],
				'compare' => '='
			)
		),
	);
	$posts = get_posts($args);



	// get the existing bookin from 'BookingId'
	$postId = $posts[0]->ID;
	$postName = $posts[0]->post_title;
	$message = "Payment due Updated";


	if ($postId) {

		$paymentduesdates = get_field('paymentduesdates', $postId);
		$payment_response = [];
		foreach ($paymentduesdates as $pr) {
			$id = $pr['id'];
			$payment_response[$id] = $pr['paymentresponse'];
		}

		$status = true;
		$FirstPayment = false;
		$DepositePayment = false;
		foreach ($fields as $key => $value) {
			$update_this_key = strtolower($key);
			// $total_rec = count($value);
			$total_rec = is_array($value) ? count($value) : 0;
			if ($key == 'PaymentDuesDates') {
				// $total_rec = count($value);
				$total_rec = is_array($value) ? count($value) : 0;
				$PaymentDuesDates  = [];
				foreach ($value as $sub_key => $sub_value) {
					$payment_id = $sub_value['Id'];
					$PaymentDuesDates[$sub_key]['id'] = $sub_value['Id'];
					$PaymentDuesDates[$sub_key]['description'] = $sub_value['Description'];
					$PaymentDuesDates[$sub_key]['amount'] = (float) $sub_value['Amount'];
					$PaymentDuesDates[$sub_key]['date'] = $sub_value['Date'];
					$PaymentDuesDates[$sub_key]['ispayment'] = $sub_value['IsPayment'];
					$PaymentDuesDates[$sub_key]['paymentresponse'] = '';
					if (isset($payment_response[$payment_id])) {
						$PaymentDuesDates[$sub_key]['paymentresponse'] = $payment_response[$payment_id];
					}

					if ($total_rec == 3 && $sub_value['Description'] == "Initial Payment Due Immediatley" && $sub_value['IsPayment']) {
						$FirstPayment = true;
					} else if ($total_rec == 2 && $sub_value['Description'] == "Rental Balance Payment" && $sub_value['IsPayment']) {
						$FirstPayment = true;
					}

					if ($sub_value['Description'] == "Security Deposit" && $sub_value['IsPayment']) {
						$DepositePayment = true;
					}
				}
				update_field($update_this_key, $PaymentDuesDates, $postId);
			}
		}

		if ($FirstPayment) {
			update_field('payment', true, $postId);
			update_field('payment_response', "Offline", $postId);
		} else {
			update_field('payment', false, $postId);
			update_field('payment_response', "", $postId);
		}

		if ($DepositePayment) {
			update_field('security_deposite_response', "Offline", $postId);
		} else {
			update_field('security_deposite_response', "", $postId);
		}
	}
	// Import End

	// Retrurn Response
	$response['Status'] = $status;
	$response['Message'] = $message;
	$response['Data'] = ['BookingId' => $fields['BookingId'], 'BookingReference' => $fields['BookingReference'], 'PostId' => $postId, 'PostName' => $postName, 'Url' => get_the_permalink($postId)];

	return json_encode($response);
}

/* concierge service */
add_action('rest_api_init', 'wp_concierge_service_booking');

function wp_concierge_service_booking()
{
	register_rest_route('api/v1', '/ConciergeServiceBooking', array(
		'methods' => 'POST',
		'callback' => 'wordpress_concierge_service_booking'
	));
}

function wordpress_concierge_service_booking($request)
{
	// Init
	$status = false;
	$fields = $request->get_params();
	$auth = apache_request_headers();
	$valid = $auth['Authorization'];

	// Validations
	if ($valid != WP_Token) {
		$response['status'] = $status;
		$response['message'] = "API Token not matched";
		$response['data'] = null;
		return json_encode($response);
	}
	if (!isset($fields['BookingId'])) {
		$response['Status'] = $status;
		$response['Message'] = "BookingReference is blank";
		$response['Data'] = null;
		return json_encode($response);
	}

	// Import Start
	$check_post_type = array('publish', 'draft', 'pending', 'future', 'private', 'inherit', 'trash');
	$set_post_status = 'publish';
	$args = array(
		'posts_per_page' => 1,
		'post_type' => 'booking',
		'post_status'   => $check_post_type,
		'meta_query' => array(
			array(
				'key' => 'BookingId',
				'value' => $fields['BookingId'],
				'compare' => '='
			)
		),
	);
	$posts = get_posts($args);

	// get the existing bookin from 'BookingId'
	$postId = $posts[0]->ID;
	$postName = $posts[0]->post_title;
	$message = "Concierge Service Updated";


	if ($postId) {
		$status = true;
		$ConciergeService = [];
		$conciergeid = $fields['ConciergeId'];
		$description = $fields['Description'];
		$conciergeservice_data = get_field('conciergeservice', $postId);

		if ($conciergeservice_data) {
			$flag = true;
			foreach ($conciergeservice_data as $key => $val) {
				if ($conciergeid == $val['conciergeid']) {
					$flag = false;
					$conciergedata = [];
					foreach ($fields['ConciergeData'] as $key2 => $val) {
						$conciergedata[$key2]['id'] = $val['Id'];
						$conciergedata[$key2]['price'] = $val['Price'];
						$conciergedata[$key2]['note'] = $val['Note'];
					}
					$ConciergeService[$key]['conciergeid'] = $conciergeid;
					$ConciergeService[$key]['description'] = $description;
					$ConciergeService[$key]['paymentresponse'] = "";
					$ConciergeService[$key]['conciergedata'] = $conciergedata;
				} else {
					$ConciergeService[$key]['conciergeid'] = $val['conciergeid'];
					$ConciergeService[$key]['description'] = $val['description'];
					$ConciergeService[$key]['paymentresponse'] = $val['paymentresponse'];
					$ConciergeService[$key]['conciergedata'] = $val['conciergedata'];
				}
			}
			if ($flag) {
				$conciergedata = [];
				foreach ($fields['ConciergeData'] as $key3 => $val) {
					$conciergedata[$key3]['id'] = $val['Id'];
					$conciergedata[$key3]['price'] = $val['Price'];
					$conciergedata[$key3]['note'] = $val['Note'];
				}
				$ConciergeService[($key + 1)]['conciergeid'] = $conciergeid;
				$ConciergeService[($key + 1)]['description'] = $description;
				$ConciergeService[($key + 1)]['paymentresponse'] = "";
				$ConciergeService[($key + 1)]['conciergedata'] = $conciergedata;
			}
		} else {
			$conciergedata = [];
			foreach ($fields['ConciergeData'] as $key4 => $val) {
				$conciergedata[$key4]['id'] = $val['Id'];
				$conciergedata[$key4]['price'] = $val['Price'];
				$conciergedata[$key4]['note'] = $val['Note'];
			}
			$ConciergeService[0]['conciergeid'] = $conciergeid;
			$ConciergeService[0]['description'] = $description;
			$ConciergeService[0]['paymentresponse'] = "";
			$ConciergeService[0]['conciergedata'] = $conciergedata;
		}

		update_field('conciergeservice', $ConciergeService, $postId);
	}
	// Import End
	$query_string = "?conciergeid=" . base64_encode($conciergeid) . "&bid=" . base64_encode($fields['BookingId']);
	$url = get_the_permalink($postId) . $query_string;

	// Retrurn Response
	$response['Status'] = $status;
	$response['Message'] = $message;
	$response['Data'] = ['BookingId' => $fields['BookingId'], 'PostId' => $postId, 'PostName' => $postName, 'Url' => $url];

	return json_encode($response);
}
