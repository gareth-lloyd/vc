<?php

// Include the api.php file for all API-related functions
require_once get_template_directory() . '/api.php';

/* Add CSS and Script to wp_head */
function theme_wp_head()
{
	/* Theme Style */
	wp_enqueue_style('theme-style.css', get_stylesheet_directory_uri() . '/style.css');

	/* Extra Style */
	wp_enqueue_style('bootstrap-min', get_stylesheet_directory_uri() . '/assets/css/bootstrap.min.css');
	wp_enqueue_style('animate-min', get_stylesheet_directory_uri() . '/assets/css/animate.min.css');
	wp_enqueue_style('owl-carousel-min', get_stylesheet_directory_uri() . '/assets/css/owl.carousel.min.css');
	wp_enqueue_style('owl-theme-default-min', get_stylesheet_directory_uri() . '/assets/css/owl.theme.default.min.css');
	wp_enqueue_style('jquery-ui', get_stylesheet_directory_uri() . '/assets/css/jquery-ui.css');
	wp_enqueue_style('lightgallery-min', get_stylesheet_directory_uri() . '/assets/css/lightgallery.min.css');
	wp_enqueue_style('daterangepicker', get_stylesheet_directory_uri() . '/assets/css/daterangepicker.css');
	wp_enqueue_style('all-min', get_stylesheet_directory_uri() . '/assets/css/all.min.css?display=swap');
	wp_enqueue_style('intlTelInput', 'https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.13/css/intlTelInput.css');
	wp_enqueue_script('trustpilot', 'https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js');

	/* Custom Style */
	wp_enqueue_style('custom-style', get_stylesheet_directory_uri() . '/assets/css/style.css');
	wp_enqueue_style('responsive-style', get_stylesheet_directory_uri() . '/assets/css/responsive.css');

	/* Jquery */
	wp_enqueue_script('jquery-min', get_stylesheet_directory_uri() . '/assets/js/jquery.min.js');
}

function booking_wp_head()
{
	/* Extra Style */
	wp_enqueue_style('bootstrap-min', get_stylesheet_directory_uri() . '/assets/css/bootstrap.min.css');
	wp_enqueue_style('jquery-ui', get_stylesheet_directory_uri() . '/assets/css/jquery-ui.css');

	/* Booking Style */
	wp_enqueue_style('custom-style', get_stylesheet_directory_uri() . '/assets/css/booking-process.css');

	/* Jquery */
	wp_enqueue_script('jquery-min', get_stylesheet_directory_uri() . '/assets/js/jquery.min.js');

	/* Flywire Payment */
	wp_enqueue_script('flywire-payment', 'https://checkout.flywire.com/flywire-payment.js');
}

/* Add Scripts to wp_footer */
function theme_wp_footer()
{
	/* Extra Scripts */
	wp_enqueue_script('popper-min', get_stylesheet_directory_uri() . '/assets/js/navigation.js');
	wp_enqueue_script('popper-min', get_stylesheet_directory_uri() . '/assets/js/popper.min.js');
	wp_enqueue_script('bootstrap-min', get_stylesheet_directory_uri() . '/assets/js/bootstrap.min.js');
	wp_enqueue_script('owl-carousel-min', get_stylesheet_directory_uri() . '/assets/js/owl.carousel.min.js');
	wp_enqueue_script('jquery-ui', get_stylesheet_directory_uri() . '/assets/js/jquery-ui.js');
	wp_enqueue_script('jquery-mixitup-min', get_stylesheet_directory_uri() . '/assets/js/jquery.mixitup.min.js');
	wp_enqueue_script('intlTelInput-jquery-min', 'https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.13/js/intlTelInput-jquery.min.js');
	wp_enqueue_script('jquery-ui-touch-punch-min', 'https://cdnjs.cloudflare.com/ajax/libs/jqueryui-touch-punch/0.2.3/jquery.ui.touch-punch.min.js');
	wp_enqueue_script('daterangepicker-min', get_stylesheet_directory_uri() . '/assets/js/daterangepicker.min.js');
	wp_enqueue_script('lightgallery-all-min', get_stylesheet_directory_uri() . '/assets/js/lightgallery-all.min.js');
	wp_enqueue_script('moment-min', get_stylesheet_directory_uri() . '/assets/js/moment.min.js');

	/* Custom Script */
	wp_enqueue_script('theme', get_stylesheet_directory_uri() . '/assets/js/theme.js');
}

// Disable auto <p> tag in CF7
add_filter('wpcf7_autop_or_not', '__return_false');

function booking_wp_footer()
{
	/* Extra Scripts */
	wp_enqueue_script('popper-min', get_stylesheet_directory_uri() . '/assets/js/popper.min.js');
	wp_enqueue_script('bootstrap-min', get_stylesheet_directory_uri() . '/assets/js/bootstrap.min.js');

	/* Booking Scripts */
	wp_enqueue_script('booking', get_stylesheet_directory_uri() . '/assets/js/booking.js');
}

function set_custom_wp_head_and_wp_footer()
{
	if (is_singular('booking')) {
		add_action('wp_enqueue_scripts', 'booking_wp_head');
		add_action('wp_footer', 'booking_wp_footer');
	} else {
		add_action('wp_enqueue_scripts', 'theme_wp_head');
		add_action('wp_footer', 'theme_wp_footer');
	}
}
add_action('wp', 'set_custom_wp_head_and_wp_footer');

function custom_theme_setup()
{
	// Automatic Feed Links
	add_theme_support('automatic-feed-links');

	// Title Tag
	add_theme_support('title-tag');

	// Post Thumbnails
	add_theme_support('post-thumbnails');

	// Register navigation menus
	register_nav_menus(
		array(
			'menu-1' => esc_html__('Primary', 'villa-collective'),
		)
	);

	// HTML5 Support
	add_theme_support(
		'html5',
		array(
			'search-form',
			'comment-form',
			'comment-list',
			'gallery',
			'caption',
			'style',
			'script',
		)
	);

	// Custom Background
	add_theme_support(
		'custom-background',
		apply_filters(
			'villa_collective_custom_background_args',
			array(
				'default-color' => 'ffffff',
				'default-image' => '',
			)
		)
	);

	// Customizer Support
	add_theme_support('customize-selective-refresh-widgets');

	// Custom Logo
	add_theme_support(
		'custom-logo',
		array(
			'height'      => 250,
			'width'       => 250,
			'flex-width'  => true,
			'flex-height' => true,
		)
	);

	// WooCommerce Support
	add_theme_support('woocommerce');
}
add_action('after_setup_theme', 'custom_theme_setup');


function villa_collective_content_width()
{
	$GLOBALS['content_width'] = apply_filters('villa_collective_content_width', 640);
}
add_action('after_setup_theme', 'villa_collective_content_width', 0);

function villa_collective_widgets_init()
{
	register_sidebar(
		array(
			'name'          => esc_html__('Sidebar', 'villa-collective'),
			'id'            => 'sidebar-1',
			'description'   => esc_html__('Add widgets here.', 'villa-collective'),
			'before_widget' => '<section id="%1$s" class="widget %2$s">',
			'after_widget'  => '</section>',
			'before_title'  => '<h2 class="widget-title">',
			'after_title'   => '</h2>',
		)
	);
}
add_action('widgets_init', 'villa_collective_widgets_init');



//Theme Panel Start
function add_theme_menu_item()
{
	add_menu_page("Theme Option", "Theme Option", "manage_options", "theme-option", "theme_settings_page", "dashicons-admin-generic", 99);
}
add_action("admin_menu", "add_theme_menu_item");

function theme_settings_page()
{
?>
	<div class="wrap">
		<h1>Theme Option</h1>
		<form method="post" action="options.php" enctype="multipart/form-data">
			<?php
			settings_fields("theme_options_group");
			do_settings_sections("theme-options");
			submit_button();
			?>
		</form>
	</div>
	<?php
}

function display_theme_panel_fields()
{
	$theme_options_group = 'theme_options_group';

	function section_callback()
	{
		echo '<p>Here you can configure various settings for your theme.</p>';
	}

	add_settings_section("section", "All Settings", "section_callback", "theme-options");

	add_settings_field("header_logo", "Header Logo:", "header_logo_field", "theme-options", "section");
	add_settings_field("footer_logo", "Footer Logo:", "footer_logo_field", "theme-options", "section");
	add_settings_field("footer_logo_1", "Footer Logo 1:", "footer_logo_1_field", "theme-options", "section");
	add_settings_field("footer_logo_2", "Footer Logo 2:", "footer_logo_2_field", "theme-options", "section");
	add_settings_field("villa_not_found", "Villa not found image:", "villa_not_found_field", "theme-options", "section");
	add_settings_field("contact_number", "Contact Number:", "contact_number_field", "theme-options", "section");
	add_settings_field("contact_time", "Contact Time:", "contact_time_field", "theme-options", "section");
	add_settings_field("header_btn_text", "Header Button Text:", "header_btn_text_field", "theme-options", "section");
	add_settings_field("map_marker", "Map Marker:", "map_marker_field", "theme-options", "section");
	add_settings_field("reduce_show", "Reduce Show:", "reduce_show_field", "theme-options", "section");
	add_settings_field("destinations_menu_cta_button_text", "Destinations Menu CTA Button Text:", "destinations_menu_cta_button_text_field", "theme-options", "section");
	add_settings_field("destinations_menu_cta_button_link", "Destinations Menu CTA Button Link:", "destinations_menu_cta_button_link_field", "theme-options", "section");
	add_settings_field("collections_menu_cta_button_text", "Collections Menu CTA Button Text:", "collections_menu_cta_button_text_field", "theme-options", "section");
	add_settings_field("collections_menu_cta_button_link", "Collections Menu CTA Button Link:", "collections_menu_cta_button_link_field", "theme-options", "section");

	register_setting($theme_options_group, "header_logo");
	register_setting($theme_options_group, "footer_logo");
	register_setting($theme_options_group, "footer_logo_1");
	register_setting($theme_options_group, "footer_logo_2");
	register_setting($theme_options_group, "villa_not_found");
	register_setting($theme_options_group, "contact_number");
	register_setting($theme_options_group, "contact_time");
	register_setting($theme_options_group, "header_btn_text");
	register_setting($theme_options_group, "map_marker");
	register_setting($theme_options_group, "reduce_show");
	register_setting($theme_options_group, "destinations_menu_cta_button_text");
	register_setting($theme_options_group, "destinations_menu_cta_button_link");
	register_setting($theme_options_group, "collections_menu_cta_button_text");
	register_setting($theme_options_group, "collections_menu_cta_button_link");
}
add_action("admin_init", "display_theme_panel_fields");

add_action('admin_head', 'theme_options_css');
function theme_options_css()
{
	echo '<style>
	.logo-upload-div a.upload-logo {
		display: inline-block;
		width: 250px;
	}
	.logo-upload-div a:focus {
		outline:0;
		border:none;
		box-shadow: none;
	}
	.logo-upload-div a img {
		max-width: 250px;
	}
	input.theme-options-input {
		width: 250px;
	}
	.taxonomy-country #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-key-feature #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-amenities #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-services_on_request #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-collections #poststuff.aioseo-taxonomy-upsell
	.taxonomy-guides-category #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-testimonials_country #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-journal-category #poststuff.aioseo-taxonomy-upsell,
	.taxonomy-category  #poststuff.aioseo-taxonomy-upsell
	{
		display:none;
	}
	.attachment-266x266, .thumbnail img {
		width: 100% !important;
		height: auto !important;
	}
	.acf-repeater .acf-row-handle.remove {
		padding: 5px !important;
	}
	.acf-repeater .acf-row-handle .acf-icon {
		margin: 2px 0 0 !important;
	}
	.post-type-booking .acf-repeater .acf-row-handle,
	.post-type-booking .acf-actions {
		display: none;
	}
	.post-type-booking .acf-repeater .acf-row:hover > .acf-row-handle .acf-icon,
	.post-type-booking .acf-repeater .acf-row.-hover > .acf-row-handle .acf-icon {
		display: none;
	}
	.post-type-booking #post-body-content {
		display: none;
	}
  </style>';
}

function header_logo_field()
{
	$image_id = get_option('header_logo');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="header_logo" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function footer_logo_field()
{
	$image_id = get_option('footer_logo');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="footer_logo" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function footer_logo_1_field()
{
	$image_id = get_option('footer_logo_1');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="footer_logo_1" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function footer_logo_2_field()
{
	$image_id = get_option('footer_logo_2');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="footer_logo_2" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function villa_not_found_field()
{
	$image_id = get_option('villa_not_found');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="villa_not_found" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function contact_number_field()
{
	echo '<input type="text" class="theme-options-input" name="contact_number" id="contact_number" value="' . get_option('contact_number') . '">';
}

function contact_time_field()
{
	echo '<input type="text" class="theme-options-input" name="contact_time" id="contact_time" value="' . get_option('contact_time') . '">';
}

function header_btn_text_field()
{
	echo '<input type="text" class="theme-options-input" name="header_btn_text" id="header_btn_text" value="' . get_option('header_btn_text') . '">';
}

function map_marker_field()
{
	$image_id = get_option('map_marker');
	$image = wp_get_attachment_image_src($image_id, 'full');
	echo '<div class="logo-upload-div">';
	if ($image) {
		echo '<a href="javascript:;" class="upload-logo"><img src="' . $image[0] . '" style="height: auto;max-width: 250px;" /></a>';
	} else {
		echo '<a href="javascript:;" class="upload-logo button button-primary">Upload image</a>';
	}
	echo '<br />';
	echo '<a href="javascript:;" class="remove-logo button" ' . ($image ? '' : 'style="display: none;"') . ' >Remove image</a>';
	echo '<input type="hidden" name="map_marker" class="logo-value" value="' . $image_id . '">';
	echo '</div>';
}

function reduce_show_field()
{
	echo '<input type="checkbox" class="theme-options-input" name="reduce_show" id="reduce_show" value="1" style="width: auto;" ' . checked(1, get_option('reduce_show'), false) . '> Reduce show on filter';
}

function destinations_menu_cta_button_text_field()
{
	echo '<input type="text" class="theme-options-input" name="destinations_menu_cta_button_text" id="destinations_menu_cta_button_text" value="' . get_option('destinations_menu_cta_button_text') . '">';
}

function destinations_menu_cta_button_link_field()
{
	echo '<input type="text" class="theme-options-input" name="destinations_menu_cta_button_link" id="destinations_menu_cta_button_link" value="' . get_option('destinations_menu_cta_button_link') . '">';
}

function collections_menu_cta_button_text_field()
{
	echo '<input type="text" class="theme-options-input" name="collections_menu_cta_button_text" id="collections_menu_cta_button_text" value="' . get_option('collections_menu_cta_button_text') . '">';
}

function collections_menu_cta_button_link_field()
{
	echo '<input type="text" class="theme-options-input" name="collections_menu_cta_button_link" id="collections_menu_cta_button_link" value="' . get_option('collections_menu_cta_button_link') . '">';
}

function image_include_js()
{
	if (!did_action('wp_enqueue_media')) {
		wp_enqueue_media();
	}
	wp_enqueue_script('admin-custom-script', get_stylesheet_directory_uri() . '/assets/js/admin-custom-script.js', array('jquery'));
}
add_action('admin_enqueue_scripts', 'image_include_js');
//Theme Panel End

// Allow SVG
add_filter('wp_check_filetype_and_ext', function ($data, $file, $filename, $mimes) {

	global $wp_version;
	if ($wp_version !== '4.7.1') {
		return $data;
	}

	$filetype = wp_check_filetype($filename, $mimes);

	return [
		'ext'             => $filetype['ext'],
		'type'            => $filetype['type'],
		'proper_filename' => $data['proper_filename']
	];
}, 10, 4);

/* Add CC Mime Type For Uploads */
function cc_mime_types($mimes)
{
	// Add SVG MIME type
	$mimes['svg'] = 'image/svg+xml';

	// Add WebP MIME type
	$mimes['webp'] = 'image/webp';

	// Add video MIME types
	$mimes['webm'] = 'video/webm';
	$mimes['mp4|m4v'] = 'video/mp4';
	$mimes['mpeg|mpg|mpe'] = 'video/mpeg';
	$mimes['ogv'] = 'video/ogg';

	return $mimes;
}
add_filter('upload_mimes', 'cc_mime_types');


// header menu add class
function add_classes_on_li($classes, $item, $args)
{
	$classes[] = 'nav-item';
	return $classes;
}
add_filter('nav_menu_css_class', 'add_classes_on_li', 1, 3);

function add_additional_class_on_a($classes, $item, $args)
{
	if (isset($args->add_a_class)) {
		$classes['class'] = $args->add_a_class;
	}
	return $classes;
}
add_filter('nav_menu_link_attributes', 'add_additional_class_on_a', 1, 3);

// Disable WordPress from generating any intermediate image sizes
function prevent_image_size_generation($sizes)
{
	// Return an empty array to prevent generating any image sizes
	return [];
}
add_filter('intermediate_image_sizes_advanced', 'prevent_image_size_generation');

// does not automatically resize or scale it down to a smaller size
add_filter('big_image_size_threshold', '__return_false');

// send to enquire
function ajax_enquire_record()
{
	$status = false;
	$message = "";

	parse_str($_POST["data"], $_POST);

	unset($_POST['daterange']);
	unset($_POST['select_date']);
	$_POST['CountryCode'] = !empty($_POST['CountryCode']) ? $_POST['CountryCode'] : 1;
	$_POST['IsSignUp'] = isset($_POST['IsSignUp']) ? true : false;
	$_POST['EnquireDateType'] = (int)$_POST['EnquireDateType'];

	// Temp change 31-12-2024 : Enquiry Draft
	$_POST['FromDate'] = !empty($_POST['FromDate']) ? date("Y-m-d", strtotime($_POST['FromDate'])) : null;
	$_POST['ToDate'] = !empty($_POST['ToDate']) ? date("Y-m-d", strtotime($_POST['ToDate'])) : null;

	if ($_POST['UserFeedback'] == 'Other') {
		$_POST['UserFeedback'] = $_POST['other_text'];
	}

	if (isset($_POST['week_range_val']) && $_POST['week_range_val'] == 7) {
		$_POST['EnquireWeek'] = '1 Week';
	} else if (isset($_POST['week_range_val']) && $_POST['week_range_val'] == 14) {
		$_POST['EnquireWeek'] = '2 Week';
	} else if (isset($_POST['week_range_val']) && $_POST['week_range_val'] == 21) {
		$_POST['EnquireWeek'] = '3 Week';
	}

	if (isset($_POST['CountryIds']) && is_array($_POST['CountryIds'])) {
		$_POST['CountryIds'] = implode(",", $_POST['CountryIds']);
	} else {
		$_POST['CountryIds'] = "";
	}

	// Region Ids (contact + wishlist forms have no RegionIds input;
	// default to the "none selected" sentinel instead of array(null))
	if (!isset($_POST['RegionIds'])) {
		$_POST['RegionIds'] = array("0");
	}
	$_POST['RegionIds'] = is_array($_POST['RegionIds']) ? $_POST['RegionIds'] : array($_POST['RegionIds']);

	unset($_POST['week_range']);
	unset($_POST['week_range_val']);
	if (isset($_POST['ContactNo'])) {
		$_POST['ContactNo'] = str_replace(' ', '', $_POST['ContactNo']);
	}

	$post_data = json_encode($_POST);

	if (trim($_POST['FirstName']) != "" && trim($_POST['LastName']) != "" && trim($_POST['Email']) != "" && trim($_POST['FromDate']) != "" && trim($_POST['ToDate']) != "" && trim($_POST['ContactNo']) != "") {

		/* ===================================
		   SAVE TO DATABASE
		=================================== */

		global $wpdb;

		$table_name = $wpdb->prefix . 'villa_enquiries';

		$result = $wpdb->insert(
			$table_name,
			array(
				'first_name'    => $_POST['FirstName'] ?? '',
				'last_name'     => $_POST['LastName'] ?? '',
				'email'         => $_POST['Email'] ?? '',
				'contact_no'    => $_POST['ContactNo'] ?? '',
				'from_date'     => $_POST['FromDate'] ?? null,
				'to_date'       => $_POST['ToDate'] ?? null,
				'adults'        => $_POST['Adults'] ?? 0,
				'children'      => $_POST['Children'] ?? 0,
				'min_bed'       => $_POST['MinBed'] ?? 0,
				'max_bed'       => $_POST['MaxBed'] ?? 0,
				'notes'         => $_POST['Notes'] ?? '',
				'referral'      => $_POST['referral'] ?? '',
				'user_feedback' => $_POST['UserFeedback'] ?? '',
				'is_signup'     => !empty($_POST['IsSignUp']) ? 1 : 0,
				'form_data'     => wp_json_encode($_POST),
			)
		);

		if ($result === false) {
			error_log('Villa Enquiry DB Error: ' . $wpdb->last_error);
		}

		/* ===================================
		   END SAVE TO DATABASE
		=================================== */

		$reference = post_enquiry_to_vc($post_data);
		if ($reference !== false) {
			$status = true;
			$message = "Your enquiry has been sent successfully";
		} else {
			// Send error mail
			$to = array(
				"connectusdemo12@gmail.com",
				"ben@mojomedia.co.uk",
				"mungraurvish@gmail.com"
			);
			$subject = "Error in enquiry form";
			$body = '
					<p>Error occurs while submitting enquiry form. Please check them.</p>

					<br><br>

					<p style="text-align:center; font-weight:bold; color:black;">
						Villa Collective
					</p>
					';
			$headers = array(
				'Content-Type: text/html; charset=UTF-8',
				'Cc: nick@villacollective.com'
			);

			wp_mail($to, $subject, $body, $headers);
			$message = "There is an issue with our form, please email us directly on info@villacollective.com with your enquiry.";
		}
		write_json_to_log(['timestamp' => current_time('mysql'), 'user_id'   => get_current_user_id(), 'event'     => 'custom_action_triggered', 'meta'      => ['key' => json_encode(['reference' => $reference])]]);
	}

	echo json_encode(['msg' => $message, 'status' => $status]);
	die();
}
add_action('wp_ajax_nopriv_ajax_enquire_record', 'ajax_enquire_record');
add_action('wp_ajax_ajax_enquire_record', 'ajax_enquire_record');

// send to wishlist
function ajax_wishlist_record()
{
	$status = false;
	$message = "";

	parse_str($_POST["data"], $_POST);
	$post_data = json_encode($_POST);

	$url = "Properties/Link";
	$response_data = post_api_call($url, $post_data);

	if (isset($response_data->status) && $response_data->status == 1) {
		$status = true;
		$message = "Your Wishlist Link Send Successfully";
	}

	echo json_encode(['msg' => $message, 'status' => $status]);
	die();
}
add_action('wp_ajax_nopriv_ajax_wishlist_record', 'ajax_wishlist_record');
add_action('wp_ajax_ajax_wishlist_record', 'ajax_wishlist_record');

// Encode and decode the id
function encode_id($id, $action)
{
	if ($action == 'encode') {
		$string = base64_encode($id);
	} else {
		$string = base64_decode($id);
	}

	return $string;
}

function redirect_direct_access()
{
	if (is_page_template('template/destination_page_template.php')) {
		$c_id = isset($_GET['c_id']) ? encode_id($_GET['c_id'], 'decode') : '';

		if (isset($_GET['c_id']) && ($c_id == '' || is_numeric($c_id) == false)) {
			wp_redirect(home_url());
			exit();
		}
	} else if (is_page_template('template/individual_collection_page_template.php')) {
		$c_id = isset($_GET['c_id']) ? encode_id($_GET['c_id'], 'decode') : '';

		if (isset($_GET['c_id']) && ($c_id == '' || is_numeric($c_id) == false)) {
			wp_redirect(home_url());
			exit();
		}
	} else if (is_page_template('template/villa_page_template.php')) {
		$v_id = isset($_GET['v_id']) ? encode_id($_GET['v_id'], 'decode') : '';

		if (!isset($_GET['v_id']) || isset($_GET['v_id']) && ($v_id == '' || is_numeric($v_id) == false)) {
			wp_redirect(home_url());
			exit();
		}
	}
}

add_action('template_redirect', 'redirect_direct_access');

// Redirect the collection 2072 or 2073 category id URL to new collection page URL
// Redirect collection term URLs to custom pages
add_action('template_redirect', function () {

	if (is_admin()) {
		return;
	}

	if (is_tax('collections')) {

		$term = get_queried_object();

		if ($term) {

			// Collection term 2072 → Page 58923
			if ($term->term_id == 2072) {

				$target_url = get_permalink(58923);

				if (trailingslashit(home_url($_SERVER['REQUEST_URI'])) !== trailingslashit($target_url)) {
					wp_safe_redirect($target_url, 301);
					exit;
				}
			}

			// Collection term 2073 → Page 59107
			if ($term->term_id == 2073) {

				$target_url = get_permalink(59107);

				if (trailingslashit(home_url($_SERVER['REQUEST_URI'])) !== trailingslashit($target_url)) {
					wp_safe_redirect($target_url, 301);
					exit;
				}
			}
		}
	}
});

// generate the string from value
function min_to_hours($value)
{
	$t = $value;
	//$return = date('H:i', mktime(0, $t)); // 01:37
	$return = date('i', mktime(0, $t)); // 25
	return $return;
}

// Create Custom Table
function create_wishlist_table()
{
	global $wpdb;
	$table_name = $wpdb->prefix . 'villa_wishlist';
	$charset_collate = $wpdb->get_charset_collate();
	$sql = "CREATE TABLE IF NOT EXISTS $table_name (
        id mediumint(9) NOT NULL AUTO_INCREMENT,
        villa_id mediumint(9) NOT NULL,
        ip_address varchar(45) NOT NULL,
        code varchar(45) NOT NULL,
        PRIMARY KEY  (id)
    ) $charset_collate;";
	require_once(ABSPATH . 'wp-admin/includes/upgrade.php');
	dbDelta($sql);
}
add_action('plugins_loaded', 'create_wishlist_table');

// Generate Unique URL with Cookie
function generate_unique_url()
{
	if (!isset($_COOKIE['wishlist_code'])) {
		$random_param = substr(str_shuffle("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), 0, 8);
		setcookie('wishlist_code', $random_param, time() + (86400 * 36500), "/"); // Expires in 100 years
	} else {
		$random_param = $_COOKIE['wishlist_code'];
	}

	$url = home_url("/wishlist/{$random_param}");
	//$link = home_url("/wishlist/?code=$random_param");

	return '<a href="' . esc_url($url) . '" target="_blank">' . esc_url($url) . '</a>';
}

// Initialize session and set wishlist_code cookie
add_action('init', 'wishlist_code', 1);
function wishlist_code()
{
	if (!session_id()) {
		session_start();
	}
	if (!isset($_COOKIE['wishlist_code'])) {
		$random_param = substr(str_shuffle("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), 0, 8);
		setcookie('wishlist_code', $random_param, time() + (86400 * 36500), "/"); // Expires in 100 years
	}
}

// add villa to wishlist
function timestamp_cookie()
{
	global $wpdb;
	$villa_id = $_POST['villa_id'];
	$ip_address = $_SERVER['REMOTE_ADDR'];
	$table_name = $wpdb->prefix . 'villa_wishlist';

	if (!isset($_COOKIE['wishlist_code'])) {
		$random_param = substr(str_shuffle("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), 0, 8);
		setcookie('wishlist_code', $random_param, time() + (86400 * 36500), "/"); // Expires in 100 years
	} else {
		$random_param = $_COOKIE['wishlist_code'];
	}

	/* Add Villa into the Cookie */
	$id = $_POST['villa_id'];
	if (!empty($_COOKIE['villa_fav'])) {
		$fav_villa[] = '';
		$fav_villa = explode(',', $_COOKIE['villa_fav']);
		if (!in_array($id, $fav_villa)) {
			array_push($fav_villa, $id);
			$fill = true;

			// If record does not exist, insert it
			$wpdb->insert(
				$table_name,
				array(
					'villa_id' => $villa_id,
					'ip_address' => $ip_address,
					'code' => $random_param
				)
			);
		} else {
			if (($key = array_search($id, $fav_villa)) !== false) {
				unset($fav_villa[$key]);
				$fill = false;

				// If record exists, delete it
				$wpdb->delete(
					$table_name,
					array('villa_id' => $villa_id, 'ip_address' => $ip_address)
				);
			}
		}

		$id = implode(",", $fav_villa);
		setcookie('villa_fav', $id, time() + (86400 * 30), "/");
	} else {

		// If record does not exist, insert it
		$wpdb->insert(
			$table_name,
			array(
				'villa_id' => $villa_id,
				'ip_address' => $ip_address,
				'code' => $random_param
			)
		);

		$fill = true;
		setcookie('villa_fav', $id, time() + (86400 * 30), "/");
	}

	$wishlist_total_items = check_wishlist_total_items();

	echo json_encode(['status' => true, 'fill' => $fill, 'wishlist_total_items' => $wishlist_total_items]);
	die();
}
add_action('wp_ajax_nopriv_timestamp_cookie', 'timestamp_cookie');
add_action('wp_ajax_timestamp_cookie', 'timestamp_cookie');

function check_wishlist_total_items()
{
	global $wpdb;
	$ip_address = sanitize_text_field($_SERVER['REMOTE_ADDR']);
	$table_name = $wpdb->prefix . 'villa_wishlist';

	$sql = "SELECT * FROM $table_name WHERE ip_address = %s ";
	$query = $wpdb->prepare($sql, array_merge([$ip_address]));

	$wishlist_items = $wpdb->get_results($query, ARRAY_A);

	$wishlist_total_items = count($wishlist_items);

	return $wishlist_total_items;
}

function set_recent_villa()
{
	$id = $_POST['villa_id'];
	if (!empty($_COOKIE['recent_villa'])) {
		$res_villa[] = '';
		$res_villa = explode(',', $_COOKIE['recent_villa']);

		if (!in_array($id, $res_villa)) {
			array_push($res_villa, $id);
		}
		$res_villa = array_slice($res_villa, -3);
		$id = implode(",", $res_villa);
	}

	setcookie('recent_villa', $id, time() + (86400 * 30), "/");

	echo json_encode(['status' => true]);
	die();
}
add_action('wp_ajax_nopriv_set_recent_villa', 'set_recent_villa');
add_action('wp_ajax_set_recent_villa', 'set_recent_villa');

function get_journal_data()
{
	$type = ($_POST['type'] == 'all') ? '' : $_POST['type'];
	$args = array(
		'post_type' => 'journal-news',
		'order' => 'ASC',
		'posts_per_page' => -1,
		'taxonomy' => 'journal-category',
		'journal-category' => $type
	);

	$post_data = get_posts($args);

	$html = '';
	foreach ($post_data as $jd_key => $jd_value) {
		$img = get_the_post_thumbnail_url($jd_value->ID, 'post-thumbnail');
		$img = !empty($img) ? $img : get_stylesheet_directory_uri() . '/assets/images/journal/journal-1.jpg';
		$category_name =  get_the_terms($jd_value->ID, 'journal-category')[0]->name;

		$html .= '<div class="col-sm-6 col-md-6 col-lg-4 col-xl-4 col-xxl-4 mix">
            <div class="journal-box">
                <div class="journal-box-img" style="background-image: url(' . $img . '"></div>
                <div class="journal-box-cnt">
                    <span>' . $category_name . '</span>
                    <h5>' . $jd_value->post_title . '</h5>
                </div>
                <div class="mt-auto">
                    <a href="' . get_the_permalink($jd_value->ID) . '" class="thm-btn-3">READ MORE</a>
                </div>
            </div>
        </div>';
	}

	echo json_encode(['status' => true, 'html' => $html]);
	die();
}
add_action('wp_ajax_nopriv_get_journal_data', 'get_journal_data');
add_action('wp_ajax_get_journal_data', 'get_journal_data');

function price_format($value)
{
	if (!empty($value)) {
		$value = preg_replace('/[^0-9]/', '', $value);
		$value = number_format($value);
	}
	return $value;
}

function redirect_404_page()
{
	if (is_404()) {
		wp_redirect("/");
		exit;
	}
}
add_action('template_redirect', 'redirect_404_page');

function custom_get_term_id($meta_key, $meta_value)
{
	global $wpdb;
	$result = $wpdb->get_row("SELECT * FROM $wpdb->termmeta WHERE meta_key = '$meta_key' AND meta_value = $meta_value");
	return $result->term_id;
}

function custom_get_post_id($meta_key, $meta_value)
{
	global $wpdb;
	$result = $wpdb->get_row("SELECT post_id FROM $wpdb->postmeta LEFT JOIN $wpdb->posts ON $wpdb->postmeta.post_id = $wpdb->posts.ID WHERE meta_key = '$meta_key' AND meta_value = $meta_value And $wpdb->posts.post_status = 'publish' ");
	return $result->post_id;
}

// get villa from wordpress
function get_villa_list_form_wordpress()
{
	$status = false;
	$filters = array();
	parse_str($_POST['data'], $filters);

	$country_id = isset($filters['country_id']) ? $filters['country_id'] : 0;
	$region_ids = isset($filters['regions_ids']) ? $filters['regions_ids'] : [];
	$collection_ids = isset($filters['CollectionIds']) ? $filters['CollectionIds'] : [];
	$keyfeatures_ids = isset($filters['KeyFeatures']) ? $filters['KeyFeatures'] : [];
	$experiences_id = isset($filters['Experiences']) ? $filters['Experiences'] : 0;
	$amenities_id = isset($filters['Amenities']) ? $filters['Amenities'] : 0;
	$minprice = isset($filters['MinPrice']) ? $filters['MinPrice'] : 0;
	$maxprice = isset($filters['MaxPrice']) ? $filters['MaxPrice'] : '';
	$minbed = isset($filters['MinBed']) ? $filters['MinBed'] : 0;
	$maxbed = isset($filters['MaxBed']) ? $filters['MaxBed'] : 23;

	$bedroom = isset($filters['bedroom']) ? $filters['bedroom'] : 0;
	$bathroom = isset($filters['bathroom']) ? $filters['bathroom'] : 0;
	$sort_by = isset($filters['sort_by']) ? $filters['sort_by'] : 0;
	$guest = isset($filters['guest']) ? $filters['guest'] : 0;
	$rtg = isset($filters['RentedTogether']) ? 1 : 0;

	// Determine sort order
	$sort = 'DESC';
	$sort_meta_key = 'minprice';
	if ($sort_by) {
		if ($sort_by == 1 || $sort_by == 3) {
			$sort = 'ASC';
		} else {
			$sort = 'DESC';
		}

		if ($sort_by == 1 || $sort_by == 2) {
			$sort_meta_key = 'maxprice';
		} else {
			$sort_meta_key = 'bedrooms';
		}
	}

	$tax_query = array('relation' => 'AND');
	if ($country_id) {
		$tax_query[] =  array(
			'taxonomy' => 'country',
			'field' => 'term_id',
			'terms' => $country_id
		);
	}

	if ($region_ids) {
		$tax_query[] =  array(
			'taxonomy' => 'country',
			'field' => 'term_id',
			'terms' => $region_ids,
			'operator' => 'IN',
		);
	}

	if ($collection_ids) {
		$tax_query[] =  array(
			'taxonomy' => 'collections',
			'field' => 'term_id',
			'terms' => $collection_ids,
			'operator' => 'IN',
		);
	}

	if ($keyfeatures_ids) {
		$key_features_query = array(
			'taxonomy' => 'key-feature',
			'field' => 'term_id',
			'terms' => $keyfeatures_ids,
			'operator' => 'IN',
		);
		$tax_query[] = $key_features_query;
	}

	if ($experiences_id) {
		$tax_query[] =  array(
			'taxonomy' => 'experience',
			'field' => 'term_id',
			'terms' => $experiences_id,
		);
	}

	if ($amenities_id) {
		$tax_query[] =  array(
			'taxonomy' => 'amenities',
			'field' => 'term_id',
			'terms' => $amenities_id,
		);
	}

	$meta_query = array('relation' => 'AND');
	if ($maxprice) {

		// As per the instruction - please use upper limit [ max price ] only, ignore min price
		/* $meta_query[] = array(
			'relation' => 'AND',
			array(
				'key' => 'minprice',
				'value' => $minprice,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
			array(
				'key' => 'maxprice',
				'value' => $maxprice,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		); */

		$meta_query[] = array(
			array(
				'key' => 'maxprice',
				'value' => $maxprice,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($minbed) {
		$meta_query[] = array(
			array(
				'key' => 'bedrooms',
				'value' => $minbed,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($maxbed) {
		$meta_query[] = array(
			array(
				'key' => 'bedrooms',
				'value' => $maxbed,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($minbed && $maxbed) {
		$meta_query[] = array(
			'relation' => 'AND',
			array(
				'key' => 'bedrooms',
				'value' => $minbed,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
			array(
				'key' => 'bedrooms',
				'value' => $maxbed,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($bedroom) {
		$meta_query[] = array(
			[
				'key'     => 'bedrooms',
				'value'   => $bedroom,
				'compare' => '=',
				'type'    => 'NUMERIC',
			]
		);
	}

	if ($bathroom) {
		$meta_query[] = array(
			[
				'key'     => 'bathroom',
				'value'   => $bathroom,
				'compare' => '=',
				'type'    => 'NUMERIC',
			]
		);
	}

	if ($guest && $guest != 0) {
		$meta_query[] = array(
			[
				'key'     => 'guest',
				'value'   => $guest,
				'compare' => '=',
				'type'    => 'NUMERIC',
			]
		);
	}

	// Live offline villa
	$meta_query[] = array(
		[
			'key' => 'villastatus',
			'value' => array('live_offline', 'archive'),
			'compare' => 'NOT IN'
		]
	);

	// Determine pagination
	$page = isset($_POST['page']) ? intval($_POST['page']) : 1;
	$posts_per_page = 12;
	$offset = ($page - 1) * $posts_per_page;

	// Main query to count total posts
	$total_args = array(
		'post_type' => 'villa-detail',
		'post_status' => 'publish',
		'tax_query' => $tax_query,
		'meta_query' => $meta_query,
		'fields' => 'ids',
		'distinct' => true,
	);
	$total_posts = new WP_Query($total_args);
	$total_villa = $total_posts->found_posts;
	wp_reset_postdata();

	// Main query to get posts
	$args = array(
		'post_type' => 'villa-detail',
		'posts_per_page' => $posts_per_page,
		'offset' => $offset,
		'orderby' => 'meta_value_num',
		'meta_key' => $sort_meta_key,
		'order' => $sort,
		'post_status' => 'publish',
		'tax_query' => $tax_query,
		'meta_query' => $meta_query,
		'fields' => 'all',
		'distinct' => true,
	);
	$query = new WP_Query($args);

	$posts = $query->posts;
	$status = !empty($posts);
	wp_reset_postdata();

	// Pagination
	$pagination = '';
	if ($total_villa > $posts_per_page * $page) {
		$nextpage = $page + 1;
		$pagination .= '<div class="col-lg-12 ' . $total_villa . '">
            <div class="pagination-btn">
                <input type="hidden" id="current_page" value="' . $page . '">
                <button type="button" class="next-btn" id="next-page" data-page="' . $nextpage . '">Load More</button>
            </div>
        </div>';
	}

	// Build response HTML
	$html = '';
	if ($page == 1) {
		$html .= '<div class="col-6">
            <div class="map-view">
                <a href="javascript:;" data-target="section-map-view">
                    <img src="' . get_stylesheet_directory_uri() . '/assets/images/map-view-icon.svg" alt="Map View" class="img-fluid">
                    Map View
                </a>
                <a href="javascript:;" data-target="section-list-view" style="display: none;">
                    <img src="' . get_stylesheet_directory_uri() . '/assets/images/list-view-icon.svg" alt="List View" class="img-fluid">
                    List
                </a>
            </div>
        </div>
        <div class="col-6">
            <div class="showing">' . $total_villa . ' VILLAS</div>
        </div>';
	}

	$html .= '<div id="section-list-view" class="col-1g-12">
        <div class="row">';
	$processed_ids = array();
	if ($status) {
		foreach ($posts as $post) {
			if (in_array($post->ID, $processed_ids)) {
				continue; // Skip duplicates
			}
			$processed_ids[] = $post->ID;
			$html .= get_villa_info_element($post->ID);
		}
	} else {
		$html .= 'No more villas';
	}
	$html .= '</div>
    </div>';

	// Location query to get all locations - changes date: 02-10-2024
	$location_total_args = array(
		'post_type' => 'villa-detail',
		'posts_per_page' => -1,
		'orderby' => 'meta_value_num',
		'meta_key' => $sort_meta_key,
		'order' => $sort,
		'post_status' => 'publish',
		'tax_query' => $tax_query,
		'meta_query' => $meta_query,
		'fields' => 'all',
		'distinct' => true,
	);
	$location_query = new WP_Query($location_total_args);
	$location_posts = $location_query->posts;

	// For Google Map
	$locations = array();
	foreach ($location_posts as $post) {
		$post_id = $post->ID;

		// For Location
		$image = get_the_post_thumbnail_url($post_id);
		$property_image = !empty($image) ? $image : get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
		$country = get_field('country', $post_id);
		$state = get_field('state', $post_id);
		$guest = get_field('guest', $post_id);
		$villa_detail_url = get_permalink($post_id);
		if (get_field('lat', $post_id) && get_field('long', $post_id)) {
			$locations[] = array(
				'id' => (int)$post_id,
				'lat' => (float)get_field('lat', $post_id),
				'lng' => (float)get_field('long', $post_id),
				'icon' => wp_get_attachment_image_src(get_option("map_marker"), "full")[0],
				'name' => addslashes($post->post_title),
				'property_image' => $property_image,
				'country' => $country,
				'state' => $state,
				'guest' => $guest,
				'link' => $villa_detail_url
			);
		}
	}

	// For Min and Max Only
	$meta_query = '';
	$min_value = PHP_INT_MAX;
	$max_value = PHP_INT_MIN;

	$meta_query = array('relation' => 'AND');
	if ($maxprice) {

		// As per the instruction - please use upper limit [ max price ] only, ignore min price
		/* $meta_query[] = array(
			'relation' => 'AND',
			array(
				'key' => 'minprice',
				'value' => $minprice,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
			array(
				'key' => 'maxprice',
				'value' => $maxprice,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		); */

		$meta_query[] = array(
			array(
				'key' => 'maxprice',
				'value' => $maxprice,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($minbed) {
		$meta_query[] = array(
			array(
				'key' => 'bedrooms',
				'value' => $minbed,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
		);
	}

	if ($minbed && $maxbed) {
		$meta_query[] = array(
			'relation' => 'AND',
			array(
				'key' => 'bedrooms',
				'value' => $minbed,
				'compare' => '>=',
				'type' => 'NUMERIC',
			),
			array(
				'key' => 'bedrooms',
				'value' => $maxbed,
				'compare' => '<=',
				'type' => 'NUMERIC',
			),
		);
	}

	// Live offline villa
	$meta_query[] = array(
		[
			'key' => 'villastatus',
			'value' => array('live_offline', 'archive'),
			'compare' => 'NOT IN'
		]
	);

	$min_max_args = array(
		'post_type' => 'villa-detail',
		'posts_per_page' => -1,
		'post_status' => 'publish',
		'orderby' => 'meta_value_num',
		'meta_key' => 'minprice',
		'tax_query' => $tax_query,
		'meta_query' => $meta_query,
	);

	$min_max_posts = get_posts($min_max_args);

	foreach ($min_max_posts as $post) {
		$minprice = get_post_meta($post->ID, 'minprice', true);
		$maxprice = get_post_meta($post->ID, 'maxprice', true);

		// Set empty values to 0
		$minprice = ($minprice === '') ? 0 : floatval($minprice);
		$maxprice = ($maxprice === '') ? 0 : floatval($maxprice);

		$min_value = min($min_value, $minprice);
		$max_value = max($max_value, $maxprice);

		// Collect all min and max prices in the temporary array
		$temp_min_values[] = $minprice;
		$temp_max_values[] = $maxprice;
	}

	// If no valid min or max values were found, set them to 0
	if ($min_value === PHP_INT_MAX) {
		$min_value = 0;
	}
	if ($max_value === PHP_INT_MIN) {
		$max_value = 0;
	}

	// If min_value is 0, find the smallest from temp_min_values
	if ($min_value === 0 && !empty($temp_min_values)) {
		$min_value = min($temp_min_values);
	}

	// If max_value is 0, find the largest from temp_max_values
	if ($max_value === 0 && !empty($temp_max_values)) {
		$max_value = max($temp_max_values);
	}

	//echo "<pre>"; print_r($locations); die;

	echo json_encode(array(
		'status' => $status,
		'html' => $html,
		'pageination' => $pagination,
		'locations' => $locations,
		'min' => $min_value,
		'max' => $max_value
	));
	wp_die(); // Properly end AJAX request
}
add_action('wp_ajax_nopriv_get_villa_list_form_wordpress', 'get_villa_list_form_wordpress');
add_action('wp_ajax_get_villa_list_form_wordpress', 'get_villa_list_form_wordpress');

// get villa in homepage
function villa_collective_from_wordpress()
{
	$status = true;
	$feature = $_POST['active_feature'];
	$fav_villa = [];
	if (isset($_COOKIE['villa_fav'])) {
		$fav_villa = explode(',', $_COOKIE['villa_fav']);
	}

	$args = array(
		'numberposts' => 5,
		'post_type' => 'villa-detail',
		'post_status' => 'publish',
		'tax_query' => array(
			array(
				'taxonomy' => 'key-feature',
				'field' => 'term_id',
				'terms' => $feature,
			),
		),
		'meta_query' => array(
			array(
				'key' => 'villastatus',
				'value' => array('live_offline', 'archive'),
				'compare' => 'NOT IN'
			)
		),
	);
	$feature_by_posts = get_posts($args);
	$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';

	$html = '';
	if ($feature_by_posts) {
		$html .= '<div class="tab-pane show active">
	        <div class="villa-collective-box">
	            <div class="row">
	                <div class="col-xxl-12">
	                    <div class="view-all-link">
	                        <a href="' . get_permalink(get_page_by_path('destinations')) . '?f_id=' . encode_id($feature, 'encode') . '">View All</a>
	                    </div>
	                </div>
	            </div>
	            <div class="row">
	                <div class="col-xxl-12">
	                    <div class="carousel-wrap">
	                        <div class="tab-slider-owl-carousel owl-carousel owl-theme">';
		foreach ($feature_by_posts as $fp_key => $fp_value) {
			$post_id = $fp_value->ID;
			$propertid = get_field('propertyid', $post_id);
			$s_image = get_the_post_thumbnail_url($post_id);
			$slider_image = !empty($s_image) ? $s_image : $image_not_found;
			$villa_price = (get_field('ispoaprice', $post_id)) ? 'POA' : get_field('currencysymbol', $post_id) . price_format(get_field('minprice', $post_id)) . ' - ' . price_format(get_field('maxprice', $post_id)) . ' / ' . get_field('pricetype', $post_id);

			$villa_detail_url = get_permalink($post_id);

			$Villa_info_div = get_villa_info_div($post_id);

			$html .= '<div class="item">
												<div class="villa-collective-sure-box">
													<a target="_blank" href="' . get_permalink($post_id) . '">
														<div class="villa-collective-sure-box-img" data-image="background-image:url(' . $slider_image . ');">
															<div class="villa-collective-info">';

			$i_class = "fa-regular fa-heart";
			if (in_array($post_id, $fav_villa)) {
				$i_class = "fa fa-heart";
			}

			$html .= category_bedge($post_id);
			$html .= '<span class="add_favourite" data-type="0" data-villa_id="' . $post_id . '"><i class="' . $i_class . '"></i></span>
															</div>
														</div>
													</a>'
				. $Villa_info_div .
				'</div>
											</div>';
		}
		$html .= '</div>
	                    </div>
	                </div>
	            </div>
	        </div>
	    </div>';

		$status = true;
	}
	echo json_encode(['html' => $html, 'status' => $status]);
	die();
}
add_action('wp_ajax_nopriv_villa_collective_from_wordpress', 'villa_collective_from_wordpress');
add_action('wp_ajax_villa_collective_from_wordpress', 'villa_collective_from_wordpress');

// Normalize the string - Remove the white space, Replace the space, and Remove the accents.
function normalizeString($str)
{
	// Step 1: Remove special characters except alphanumeric and spaces
	$str = preg_replace('/[^\p{L}0-9\s-]/u', '', $str);

	// Step 2: Replace consecutive spaces with a single space
	$str = preg_replace('/\s+/', ' ', $str);

	// Step 3: Replace spaces with hyphens
	$str = str_replace(' ', '-', $str);

	// Step 4: Transliterate accented characters
	if (class_exists('Transliterator')) {
		$str = Transliterator::createFromRules(
			':: NFD; :: [: Nonspacing Mark :] Remove; :: NFC;',
			Transliterator::FORWARD
		)->transliterate($str);
	} else {
		// Fallback: Remove accents without transliteration
		$str = preg_replace('/\p{Mn}/u', '', normalizer_normalize($str, Normalizer::FORM_D));
	}

	// Step 5: Convert to lowercase
	$str = strtolower($str);

	return $str;
}

// villa search
function ajax_live_search_form_wp()
{
	$query = $_POST['q'];
	$target_id = $_POST['target_id'];
	$status = false;
	$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
	if (empty($query)) {
		echo json_encode(['status' => $status]);
		die();
	}

	$taxonomy_name = 'country';
	$country_list = custom_get_term_by_name($query, $taxonomy_name);
	$html = '';

	if ($country_list) {
		$args = array(
			'numberposts' => 3,
			'post_type' => 'villa-detail',
			'post_status' => 'publish',
			'tax_query' => array(
				array(
					'taxonomy' => $taxonomy_name,
					'field' => 'term_id',
					'terms' => $country_list[0]->term_id,
				),
			),
			'meta_query' => array(
				array(
					'key' => 'villastatus',
					'value' => 'live_offline',
					'compare' => '!='
				)
			),
		);

		$country_list_args_check_point =  get_posts($args);
		if (empty($country_list_args_check_point)) {

			// search from all villa
			$args = array(
				'numberposts' => 3,
				'post_type' => 'villa-detail',
				'post_status' => 'publish',
				's' => $query,
				'meta_query' => array(
					array(
						'key' => 'villastatus',
						'value' => 'live_offline',
						'compare' => '!='
					)
				)
			);
		}

		$regions = [];

		$destinations_html = '';
		foreach ($country_list as $cl_key => $cl_value) {
			if ($cl_value->parent != 0) {
				continue;
			} // SKIP IF NOT COUNTRY
			$regions[$cl_value->term_id] = get_term_children($cl_value->term_id, 'country');
			$destinations_html .= '<div class="form-check"><a href="' . home_url(normalizeString($cl_value->name)) . '" class="destination-link top">' . $cl_value->name . '</a></div>';

			/* Mobile Search Hidden Field */
			if ($target_id == 'header_search_mobile') {
				$destinations_html .= '<input type="hidden" name="destination" value="' . $cl_value->term_id . '">';
			}
		}

		$regions_html = '';
		foreach ($regions as $r_key => $r_value) {
			foreach ($r_value as $r_k => $r_v) {
				$r_destination_id = get_term($r_v)->parent;
				$r_destination = get_term($r_destination_id)->name;
				$regions_html .= '<div class="form-check"><a href="' . home_url(normalizeString($r_destination) . '/' . normalizeString(get_term($r_v)->name)) . '" class="region-link top">' . get_term($r_v)->name . '</a></div>';

				/* Mobile Search Hidden Field */
				if ($target_id == 'header_search_mobile') {
					$regions_html .= '<input type="hidden" name="regions[]" value="' . $r_v . '">';
				}
			}
		}
	} else {
		$args = array(
			'numberposts' => 3,
			'post_type' => 'villa-detail',
			'post_status' => 'publish',
			's' => $query,
			'meta_query' => array(
				array(
					'key' => 'villastatus',
					'value' => 'live_offline',
					'compare' => '!='
				)
			)
		);
	}

	$posts_by_name = get_posts($args);
	$postID = $posts_by_name[0]->ID;

	if (empty($posts_by_name)) {
		$html .= '<ul><li>
		<h6><span class="search-no-results">Press Enter to view all destinations</span></h6>
		</li></ul>';
		echo json_encode(['html' => $html, 'status' => $status]);
		die();
	}

	if (empty($destinations_html)) {
		$country_list = wp_get_post_terms($postID, 'country');

		$destinations_html = '';
		$regions_html = '';
		foreach ($country_list as $cl_key => $cl_value) {
			if ($cl_value->parent == 0) {
				$destinations_html .= '<div class="form-check"><a href="' . home_url(normalizeString($cl_value->name)) . '" class="destination-link bottom">' . $cl_value->name . '</a></div>';

				/* Mobile Search Hidden Field */
				if ($target_id == 'header_search_mobile') {
					$destinations_html .= '<input type="hidden" name="destination" value="' . $cl_value->term_id . '">';
				}
			} else {
				$r_key = $cl_value->parent;
				$r_v = $cl_value->term_id;

				$r_destination_id = get_term($r_v)->parent;
				$r_destination = get_term($r_destination_id)->name;

				$regions_html .= '<div class="form-check"><a href="' . home_url(normalizeString($r_destination) . '/' . normalizeString(get_term($r_v)->name)) . '" class="region-link bottom">' . get_term($r_v)->name . '</a></div>';

				/* Mobile Search Hidden Field */
				if ($target_id == 'header_search_mobile') {
					$regions_html .= '<input type="hidden" name="regions[]" value="' . $r_v . '">';
				}
			}
		}
	}

	$properties_html = '';
	foreach ($posts_by_name as $post_key => $post_value) {
		$post_id = $post_value->ID;
		$villa_detail_url = get_permalink($post_id);
		$image = get_the_post_thumbnail_url($post_id);
		$property_image = !empty($image) ? $image : $image_not_found;
		$guest = get_field('guest', $post_id);
		$guest_str = ($guest > 1) ? 'GUESTS' : 'GUEST';

		$properties_html .= '<a href="' . $villa_detail_url . '">
							<div class="sub-villa">
								<input type="hidden" value="' . get_the_title($post_id) . ', ' . get_field('country', $post_id) . ', ' . get_field('state', $post_id) . '" name="villa_detail_name">
								<img src="' . $property_image . '" alt="" class="img-fluid">
								<div class="sub-villa-cnt">
									<span>' . get_field('country', $post_id) . ', ' . get_field('state', $post_id) . '</span>
									<h6>' . get_the_title($post_id) . '</h6>
									<div class="d-flex align-items-center">
										<div class="sub-villa-amenities">' . $guest . ' ' . $guest_str . '</div>
									</div>
								</div>
							</div>
						</a>';
	}

	$html .= '<ul>
				<li>
					<h6>DESTINATION</h6>
					' . $destinations_html . '
				</li>
				<li class="filter-region">
					<h6>REGION</h6>
					' . $regions_html . '
				</li>';

	if (!empty($collections_html)) {
		$html .= '<li>
					<h6>COLLECTIONS</h6>
					' . $collections_html . '
				</li>';
	}


	if (!empty($properties_html)) {
		$html .= '<li>
				<h6>VILLAS</h6>
				' . $properties_html . '
			</li>';
	}

	$html .= '</ul>';

	$status = true;
	echo json_encode(['html' => $html, 'status' => $status]);
	die();
}
add_action('wp_ajax_nopriv_ajax_live_search_form_wp', 'ajax_live_search_form_wp');
add_action('wp_ajax_ajax_live_search_form_wp', 'ajax_live_search_form_wp');

function custom_get_term_by_name($term_name, $taxonomy_name)
{
	global $wpdb;
	$result = $wpdb->get_results("SELECT * FROM wp_terms as wt LEFT JOIN wp_term_taxonomy as wtt ON wt.term_id = wtt.term_id WHERE wt.name LIKE '$term_name%' AND wtt.taxonomy = '$taxonomy_name' ");
	return $result;
}

// get or upload the image and return attachment id
function get_or_upload_image($file_name, $PropertyId)
{

	$upload_dir = wp_upload_dir();
	$file = $upload_dir['basedir'] . '/villa-image/' . $PropertyId . '/' . $file_name;
	$wp_upload_path = $upload_dir['baseurl'] . '/villa-image/' . $PropertyId . '/';
	$res_base_url = (WP_SITE_ENV == 'Local') ? 'https://192.168.0.111/PropertyImages/' . $PropertyId . '/' : 'https://vc2.mojodev.co.uk/PropertyImages/' . $PropertyId . '/';

	if (!file_exists($file)) {
		$image_url = $res_base_url . $file_name;
		$image = pathinfo($image_url);
		$image_name = $image['basename'];

		$image_data = (WP_SITE_ENV == 'Local')
			? file_get_contents($image_url, false, stream_context_create(['ssl' => ['verify_peer' => false, 'verify_peer_name' => false]]))
			: file_get_contents($image_url);

		if (!empty($image_data)) {
			$unique_file_name = wp_unique_filename($upload_dir['path'], $image_name);
			wp_mkdir_p($upload_dir['basedir'] . '/villa-image/' . $PropertyId);
			$file = $upload_dir['basedir'] . '/villa-image/' . $PropertyId . '/' . basename($unique_file_name);
			file_put_contents($file, $image_data);

			$wp_filetype = wp_check_filetype($unique_file_name, null);
			$attachment = [
				'post_mime_type' => $wp_filetype['type'],
				'post_title' => sanitize_file_name($unique_file_name),
				'post_content' => '',
				'post_status' => 'inherit',
			];

			$attachment_id = wp_insert_attachment($attachment, $file);
			require_once ABSPATH . 'wp-admin/includes/image.php';
			$attach_data = wp_generate_attachment_metadata($attachment_id, $file);
			wp_update_attachment_metadata($attachment_id, $attach_data);
		}
	} else {
		$image_url = $wp_upload_path . $file_name;
		$attachment_id = attachment_url_to_postid($image_url);
	}

	return $attachment_id;
}

function reorder_villa_detail_list($q)
{
	if (!is_admin() || !$q->is_main_query()) {
		return;
	}
	$s = get_current_screen();
	if ($s->base === 'edit' && $s->post_type === 'villa-detail') {
		if (!isset($_GET['orderby'])) {
			$q->set('orderby', 'title');
			$q->set('order', 'ASC');
		}
	}
}
add_action('pre_get_posts', 'reorder_villa_detail_list');

function filter_post_by_country()
{
	global $typenow;
	$post_type = 'villa-detail';
	$taxonomy  = 'country';
	if ($typenow == $post_type) {
		$selected      = isset($_GET[$taxonomy]) ? $_GET[$taxonomy] : '';
		$info_taxonomy = get_taxonomy($taxonomy);
		wp_dropdown_categories(array(
			'show_option_all' => __("Filter by Country/Regions"),
			'taxonomy'        => $taxonomy,
			'name'            => $taxonomy,
			'selected'        => $selected,
			'show_count'      => true,
			'hide_empty'      => true,
		));
	};
}
add_action('restrict_manage_posts', 'filter_post_by_country');

function set_country_filter($query)
{
	global $pagenow;
	$qv = &$query->query_vars;
	if ($pagenow == 'edit.php' && isset($qv['country']) && ctype_digit($qv['country'])) {
		if ($term = get_term_by('id', $qv['country'], 'country')) {
			$qv['country'] = $term->slug;
		}
	}
}
add_filter('parse_query', 'set_country_filter');

function filter_post_by_property_id()
{
	global $typenow;
	$post_type = 'villa-detail';
	if ($typenow == $post_type) { ?>
		<input type="text" name="property_id" id="property_id" placeholder="Search by Property ID" value="<?php echo isset($_GET['property_id']) ? esc_attr($_GET['property_id']) : ''; ?>" />
	<?php
	}
}
add_action('restrict_manage_posts', 'filter_post_by_property_id');

function set_property_id_filter($query)
{
	global $pagenow;
	if ($pagenow == 'edit.php' && isset($_GET['property_id']) && !empty($_GET['property_id'])) {
		$property_id = sanitize_text_field($_GET['property_id']);
		$meta_query = array(
			array(
				'key'     => 'PropertyId',
				'value'   => $property_id,
				'compare' => 'LIKE'
			)
		);

		if (isset($query->query_vars['meta_query'])) {
			$query->query_vars['meta_query'][] = $meta_query[0];
		} else {
			$query->query_vars['meta_query'] = $meta_query;
		}
	}
}
add_filter('pre_get_posts', 'set_property_id_filter');

function custom_get_min_max_price($type)
{
	global $wpdb;

	$min_value = 0;
	$max_value = 100000;

	$result_min = $wpdb->get_row("SELECT MIN(CAST(meta_value AS SIGNED)) as min FROM `wp_postmeta` WHERE `meta_key` = 'minprice'");
	if ($result_min && isset($result_min->min)) {
		$min_value = $result_min->min;
	}

	if ($type == 'max') {
		$result_max = $wpdb->get_row("SELECT MAX(CAST(meta_value AS SIGNED)) as max FROM `wp_postmeta` WHERE `meta_key` = 'maxprice'");
		if ($result_max && isset($result_max->max)) {
			$max_value = $result_max->max;
		}
	}

	return ($type == 'max') ? $max_value : $min_value;
}
add_action('wp_ajax_nopriv_custom_get_min_max_price', 'custom_get_min_max_price');
add_action('wp_ajax_custom_get_min_max_price', 'custom_get_min_max_price');

function getrenttotalroom($villaids = [])
{
	$total = 0;
	foreach ($villaids as $ids) {
		$total += get_field('bedrooms', $ids);
	}
	return $total;
}

function get_villa_info_div($post_id)
{
	$html = '';
	$villa_detail_url = get_permalink($post_id);
	$state = get_field('state', $post_id);
	$country = get_field('country', $post_id);
	$currencysymboldisplay = get_field('currencysymboldisplay', $post_id);
	$ispoaprice = get_field('ispoaprice', $post_id);
	$currencysymbol = get_field('currencysymbol', $post_id);
	$minprice = get_field('minprice', $post_id);
	$maxprice = get_field('maxprice', $post_id);
	$maxprice = ($maxprice) ? ' - ' . price_format($maxprice) : '';
	$pricetype = get_field('pricetype', $post_id);
	$pricetype = ($pricetype) ? ' / ' . $pricetype : '';
	$guest = get_field('guest', $post_id);
	$guest_str = ($guest > 1) ? 'GUESTS' : 'GUEST';
	$additionalguest = get_field('additionalguest', $post_id);
	$addguest = !empty($additionalguest) ? '+' . $additionalguest : '';

	$bedrooms = get_field('bedrooms', $post_id);
	$bedroom_str = ($bedrooms > 1) ? 'BEDROOMS' : 'BEDROOM';

	$bathroom = get_field('bathroom', $post_id);
	$bathroom_str = ($bathroom > 1) ? 'BATHROOMS' : 'BATHROOM';

	$villa_price = ($ispoaprice) ? 'Price on request' : $currencysymbol . price_format($minprice) . $maxprice  . $pricetype;
	if ($currencysymboldisplay) {
		$villa_price = ($ispoaprice) ? 'Price on request' : price_format($minprice) . $maxprice . $currencysymbol . $pricetype;
	}

	$html .= '<a href="' . $villa_detail_url . '" target="_blank">
        <div class="villa-collective-cnt">
            <span>' . $state . ', ' . $country . '</span>
            <div class="villa-collective-head">
                <h3>' . get_the_title($post_id) . '</h3>
            </div>            
			<div class="mt-auto">    
				<div class="amount">' . $villa_price . '</div>
		        <div class="row justify-content-center">
		            <div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
		                <div class="villa-collective-amenity">
		                    <span class="h6">' . $guest . $addguest . '</span>
		                    <span>' . $guest_str . '</span>
		                </div>
		            </div>
		            <div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
		                <div class="villa-collective-amenity">
		                    <span class="h6">' . $bedrooms . '</span>
		                    <span>' . $bedroom_str . '</span>
		                </div>
		            </div>
		            <div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
		                <div class="villa-collective-amenity">
		                    <span class="h6">' . $bathroom . '</span>
		                    <span>' . $bathroom_str . '</span>
		                </div>
		            </div>
		        </div>
		    </div>
        </div>
    </a>';

	return $html;
}

function get_villa_info_element($post_id)
{
	$html = '';

	$fav_villa = isset($_COOKIE['villa_fav']) ? explode(',', $_COOKIE['villa_fav']) : [];
	$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
	$villa_detail_url = get_permalink($post_id);
	$state = get_field('state', $post_id);
	$country = get_field('country', $post_id);
	$currencysymboldisplay = get_field('currencysymboldisplay', $post_id);
	$ispoaprice = get_field('ispoaprice', $post_id);
	$currencysymbol = get_field('currencysymbol', $post_id);
	$minprice = get_field('minprice', $post_id);
	$maxprice = get_field('maxprice', $post_id);
	$maxprice = ($maxprice) ? ' - ' . price_format($maxprice) : '';
	$pricetype = get_field('pricetype', $post_id);
	$pricetype = ($pricetype) ? ' / ' . $pricetype : '';
	$guest = get_field('guest', $post_id);
	$guest_str = ($guest > 1) ? 'GUESTS' : 'GUEST';
	$additionalguest = get_field('additionalguest', $post_id);
	$addguest = !empty($additionalguest) ? '+' . $additionalguest : '';
	$bedrooms = get_field('bedrooms', $post_id);
	$bedroom_str = ($bedrooms > 1) ? 'BEDROOMS' : 'BEDROOM';
	$bathroom = get_field('bathroom', $post_id);
	$bathroom_str = ($bathroom > 1) ? 'BATHROOMS' : 'BATHROOM';

	$propertyimages_slider = [];
	$propertyimage = get_the_post_thumbnail_url($post_id);
	$inter = get_field('interiorimages', $post_id);
	$exter = get_field('exteriorimages', $post_id);
	if ($propertyimage) {
		$propertyimages_slider[] = $propertyimage;
	}
	if ($exter) {
		foreach ($exter as $value) {
			$propertyimages_slider[] = $value;
		}
	}
	if ($inter) {
		foreach ($inter as $value) {
			$propertyimages_slider[] = $value;
		}
	}

	$image = !empty($propertyimage) ? $propertyimage : $image_not_found;
	$i_class = in_array($post_id, $fav_villa) ? "fa fa-heart" : "fa-regular fa-heart";
	$villa_price = ($ispoaprice) ? 'Price on request' : ($currencysymboldisplay ? price_format($minprice) . $maxprice . $currencysymbol . $pricetype : $currencysymbol . price_format($minprice) . $maxprice . $pricetype);

	$html .= '<div class="col-sm-6 col-md-6 col-lg-6 col-xl-6 col-xxl-4 mb-48 animate__animated animate__slideInUp">
				<div class="villa-collective-sure-box">';
	if (!empty($propertyimages_slider)) {
		$html .= '<div class="villa-collective-sure-slider">
					<div class="villa-collective-info">
						' . category_bedge($post_id) . '
						<span class="add_favourite" data-type="0" data-villa_id="' . $post_id . '"><i class="' . $i_class . '"></i></span>
					</div>
            		<div class="carousel-wrap">
                		<div class="villa-collective-slider owl-carousel owl-theme">';
		foreach ($propertyimages_slider as $slider_image) {
			$html .= '<div class="item">
											<a href="' . $villa_detail_url . '" target="_blank"> 
												<div class="villa-collective-sure-box-img-slider" data-image="background-image:url(' . $slider_image . ');"></div>
											</a>
										</div>';
		}
		$html .= '</div>
            		</div>
        		</div>';
	} else {
		$html .= '<a href="' . $villa_detail_url . '" target="_blank">
					<div class="villa-collective-sure-box-img" style="background-image:url(' . $image . ');"></div>
        		</a>
				<div class="villa-collective-info">
					' . category_bedge($post_id) . '
					<span class="add_favourite" data-type="0" data-villa_id="' . $post_id . '"><i class="' . $i_class . '"></i></span>
				</div>';
	}
	$html .= '<a href="' . $villa_detail_url . '" target="_blank">
				<div class="villa-collective-cnt">
					<span>' . $state . ', ' . $country . '</span>
					<div class="villa-collective-head">
						<h3>' . get_the_title($post_id) . '</h3>
					</div>            
					<div class="mt-auto">    
						<div class="amount">' . $villa_price . '</div>
						<div class="row justify-content-center">
							<div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
								<div class="villa-collective-amenity">
									<span class="h6">' . $guest . $addguest . '</span>
									<span>' . $guest_str . '</span>
								</div>
							</div>
							<div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
								<div class="villa-collective-amenity">
									<span class="h6">' . $bedrooms . '</span>
									<span>' . $bedroom_str . '</span>
								</div>
							</div>
							<div class="col-4 col-sm-4 col-md-4 col-lg-4 col-xxl-4">
								<div class="villa-collective-amenity">
									<span class="h6">' . $bathroom . '</span>
									<span>' . $bathroom_str . '</span>
								</div>
							</div>
						</div>
					</div>
				</div>
    		</a>
    	</div>
	</div>';

	return $html;
}

// Display Category bedge - ignore NotSet
function category_bedge($post_id)
{

	$category = get_field('category', $post_id);
	$check_point = strtolower($category);

	$catgory_flag = false;
	if (!empty($check_point) && $check_point != '' && $check_point != null && $check_point != 'null') {
		if ($check_point != 'notset') {
			$catgory_flag = true;
		}
	}

	$category_bedge = ($catgory_flag) ? '<div class="label ' . $check_point . '">' . $category . '</div>' : '';

	return $category_bedge;
}

/* Villa Staus - Start */
function my_custom_status_creation()
{
	// Register the new statuses
	register_post_status('live_offline', array(
		'label' => _x('Live Offline', 'post'),
		'label_count' => _n_noop('Live Offline <span class="count">(%s)</span>', 'Live Offline <span class="count">(%s)</span>'),
		'public' => true,
		'exclude_from_search' => true,
		'show_in_admin_all_list' => true,
		'show_in_admin_status_list' => true
	));

	register_post_status('archive', array(
		'label' => _x('Archive', 'post'),
		'label_count' => _n_noop('Archive <span class="count">(%s)</span>', 'Archive <span class="count">(%s)</span>'),
		'public' => true,
		'exclude_from_search' => true,
		'show_in_admin_all_list' => true,
		'show_in_admin_status_list' => true
	));
}
add_action('init', 'my_custom_status_creation');

function add_to_post_status_dropdown()
{
	global $post;
	if ($post->post_type != 'villa-detail')
		return false;

	$status = ($post->post_status == 'live_offline') ?
		"jQuery('#post-status-display').text('Live Offline');
         jQuery('select[name=\"post_status\"]').val('live_offline');" : (($post->post_status == 'archive') ?
			"jQuery('#post-status-display').text('Archive');
         jQuery('select[name=\"post_status\"]').val('archive');" : '');

	echo "<script>
            jQuery(document).ready(function() {
                jQuery('select[name=\"post_status\"]').append('<option value=\"live_offline\">Live Offline</option>');
                jQuery('select[name=\"post_status\"]').append('<option value=\"archive\">Archive</option>');
                " . $status . "
            });
        </script>";
}
add_action('post_submitbox_misc_actions', 'add_to_post_status_dropdown');

function custom_status_add_in_quick_edit()
{
	global $post;
	if (!isset($post) || !is_object($post) || $post->post_type != 'villa-detail') {
		return false;
	}

	echo "<script>
            jQuery(document).ready(function() {
                jQuery('select[name=\"_status\"]').append('<option value=\"live_offline\">Live Offline</option>');
                jQuery('select[name=\"_status\"]').append('<option value=\"archive\">Archive</option>');
            });
        </script>";
}
add_action('admin_footer-edit.php', 'custom_status_add_in_quick_edit');

function display_archive_state($states)
{
	global $post;
	$arg = get_query_var('post_status');
	if ($arg != 'live_offline' && $arg != 'archive') {
		if (isset($post) && is_object($post) && isset($post->post_status) && $post->post_status == 'live_offline') {
			echo "<script>
                jQuery(document).ready(function() {
                    jQuery('#post-status-display').text('Live Offline');
                });
            </script>";
			return array('Live Offline');
		} elseif (isset($post) && is_object($post) && isset($post->post_status) && $post->post_status == 'archive') {
			echo "<script>
                jQuery(document).ready(function() {
                    jQuery('#post-status-display').text('Archive');
                });
            </script>";
			return array('Archive');
		}
	}
	return $states;
}
add_filter('display_post_states', 'display_archive_state');

// Exclude posts from sitemap if custom field 'villastatus' equals 'live_offline'
function exclude_villastatus_from_sitemap($query)
{
	if (!is_admin() && $query->is_main_query()) {
		if (is_post_type_archive('villa-detail') || is_singular('villa-detail')) {
			$meta_query = array(
				array(
					'key'     => 'villastatus',
					'value'   => 'live_offline',
					'compare' => '!=',
				)
			);
			$query->set('meta_query', $meta_query);
		}
	}
}
add_action('pre_get_posts', 'exclude_villastatus_from_sitemap');

// Exclude posts from sitemap based on custom field 'villastatus'
add_filter('xmlsitemap_exclude_post', function ($exclude, $post) {
	$villastatus = get_post_meta($post->ID, 'villastatus', true);
	if ($villastatus == 'live_offline') {
		return true;
	}
	return $exclude;
}, 10, 2);

// Add noindex meta tag if custom field 'villastatus' equals 'live_offline'
function add_noindex_for_villastatus()
{
	if (is_single()) {
		$villastatus = get_post_meta(get_the_ID(), 'villastatus', true);
		if ($villastatus == 'live_offline') {
			echo '<meta name="robots" content="noindex, nofollow">';
		}
	}
}
add_action('wp_head', 'add_noindex_for_villastatus');

// change label Published to Live Online and Removed mine tab
function change_villa_detail_views($views)
{
	if (isset($_GET['post_type']) && $_GET['post_type'] === 'villa-detail') {

		// Remove the 'Published' tab
		if (isset($views['publish'])) {
			unset($views['publish']);
		}

		// Remove the 'Mine' tab
		if (isset($views['mine'])) {
			unset($views['mine']);
		}

		// Get the count of posts with 'villastatus' = 'live_online' or is empty
		$live_online_count = get_live_online_count();

		// Get the count of posts with 'villastatus' = 'live_offline'
		$live_offline_count = get_posts_count_by_villastatus('live_offline');

		// Remove the 'post_status' parameter from the URL
		$base_url = remove_query_arg('post_status', add_query_arg('post_type', 'villa-detail', admin_url('edit.php')));

		// Add a new tab for 'Live Online'
		$current_live_online = isset($_GET['villa_status']) && $_GET['villa_status'] === 'live_online' ? ' class="current"' : '';
		$views['live_online'] = '<a href="' . esc_url(add_query_arg('villa_status', 'live_online', $base_url)) . '"' . $current_live_online . '>Live Online <span class="count">(' . $live_online_count . ')</span></a>';

		if ($live_offline_count > 0) {
			// Add a new tab for 'Live Offline'
			$current_live_offline = isset($_GET['villa_status']) && $_GET['villa_status'] === 'live_offline' ? ' class="current"' : '';
			$views['live_offline'] = '<a href="' . esc_url(add_query_arg('villa_status', 'live_offline', $base_url)) . '"' . $current_live_offline . '>Live Offline <span class="count">(' . $live_offline_count . ')</span></a>';
		}

		return $views;
	}
	return $views;
}
add_filter('views_edit-villa-detail', 'change_villa_detail_views');

// Get the count of posts with 'villastatus' = 'live_online' or is empty
function get_live_online_count()
{
	global $wpdb;

	$query = $wpdb->prepare("
        SELECT COUNT(*) 
        FROM $wpdb->posts p
        LEFT JOIN $wpdb->postmeta pm ON p.ID = pm.post_id AND pm.meta_key = 'villastatus' 
        WHERE p.post_type = %s 
        AND p.post_status = %s 
        AND (pm.meta_value = 'live_online' OR pm.meta_value IS NULL OR pm.meta_value = '') 
    ", 'villa-detail', 'publish');

	return $wpdb->get_var($query);
}

// Get the count of posts with a specific 'villastatus'
function get_posts_count_by_villastatus($status)
{
	$args = array(
		'post_type'  => 'villa-detail',
		'post_status' => 'publish',
		'meta_query' => array(
			array(
				'key'     => 'villastatus',
				'value'   => $status,
				'compare' => '='
			)
		),
		'fields' => 'ids',
		'posts_per_page' => -1
	);

	$query = new WP_Query($args);
	return $query->post_count;
}

// Modify the query based on the custom tab
function filter_villa_detail_by_status($query)
{
	if (!is_admin() || !$query->is_main_query() || $query->get('post_type') !== 'villa-detail') {
		return;
	}

	// Check if a villa_status is set and apply the meta query
	if (isset($_GET['villa_status'])) {

		$query->set('post_status', 'publish');
		$villa_status = sanitize_text_field($_GET['villa_status']);
		if ($villa_status === 'live_online') {
			$query->set('meta_query', array(
				'relation' => 'OR',
				array(
					'key'     => 'villastatus',
					'value'   => 'live_online',
					'compare' => '='
				),
				array(
					'key'     => 'villastatus',
					'value'   => '',
					'compare' => '='
				),
				array(
					'key'     => 'villastatus',
					'compare' => 'NOT EXISTS'
				)
			));
		}
		if ($villa_status === 'live_offline') {
			$query->set('meta_query', array(
				array(
					'key'     => 'villastatus',
					'value'   => $villa_status,
					'compare' => '='
				)
			));
		}
	}
}
add_action('pre_get_posts', 'filter_villa_detail_by_status');
/* Villa Staus - End */

/* Mobile Search - Start */
function mobile_search()
{
	$country_terms = get_terms([
		'taxonomy' => 'country',
		'hide_empty' => true,
		'parent' => 0,
		'meta_query' => array(
			[
				'key' => 'country_enable',
				'value' => 1,
				'compare' => '=',
			]
		),
	]);
	?>
	<form action="<?= get_permalink(get_page_by_path('destinations')) ?>" method="POST">
		<div id="mySidepanel" class="sidepanel">
			<div class="modal-body-cnt">
				<div class="header-search">
					<div class="header-search-mobile">
						<input type="text" class="form-control input-search" id="header_search_mobile" placeholder="Search">
						<i class="fa-solid fa-magnifying-glass"></i>
						<i class="fa-solid fa-xmark closebtn" onclick="closeNav()"></i>
					</div>
					<div class="sub-filter header_sub_filter" id="header_sub_filter"></div>
				</div>
			</div>
		</div>
	</form>
	<?php
}
/* Mobile Search - End */

/* Get All Journal - Start */
function get_all_journal()
{
	$args = array(
		'post_type'      => 'journal-news',
		'post_status'    => 'publish',
		'post__not_in'   => array(get_the_ID()),
		'posts_per_page' => 2,
		'meta_query'     => array(
			array(
				'key'   => 'is_featured',
				'value' => true,
				'compare' => '='
			),
		),
		'orderby'       => 'modified',
		'order'         => 'DESC',
	);

	$explore = get_posts($args);
	$get_explore_count = count($explore);

	if ($get_explore_count < 2) {

		$ids = array();
		foreach ($explore as $post) {
			$ids[] = $post->ID;
		}

		$args = array(
			'post_type'      => 'journal-news',
			'post_status'    => 'publish',
			'posts_per_page' => 2 - $get_explore_count,
			'post__not_in'   => $ids,
			'orderby'        => 'date',
			'order'          => 'DESC',
		);
		$explore = get_posts($args);
	}

	foreach ($explore as $key => $value) {

		$image = get_the_post_thumbnail_url($value->ID, 'post-thumbnail');
		$image = !empty($image) ? $image : get_stylesheet_directory_uri() . '/assets/images/journal/journal-1.jpg';

		$title = get_the_title($value->ID);
		$excerpt = get_the_excerpt($value->ID);
		$permalink = get_permalink($value->ID);
	?>
		<div class="col-md-12 col-lg-6 col-xl-6 col-xxl-6 text-center animate__animated animate__fadeInLeft">
			<div class="explore-the-journal-box">
				<a href="<?= esc_url($permalink) ?>">
					<div class="explore-the-journal-img" style="background-image:url(<?= $image ?>);"></div>
				</a>
				<div class="explore-the-journal-cnt">
					<a href="<?= esc_url($permalink) ?>"><span><?= $title ?></span></a>
					<span class="h6">
						<?= $excerpt ?>
					</span>
				</div>
			</div>
		</div>
	<?php }
}
/* Get All Journal - End */

/* Add Villa Status Column into the Lising */
add_filter('manage_villa-detail_posts_columns', 'add_villa_status_column');
function add_villa_status_column($columns)
{
	$new_columns = [];
	foreach ($columns as $key => $value) {
		if ($key === 'date') {
			$new_columns['villastatus'] = __('Villa Status', 'villa-collective');
		}
		$new_columns[$key] = $value;
	}
	return $new_columns;
}

add_action('manage_villa-detail_posts_custom_column', 'populate_villa_status_column', 10, 2);
function populate_villa_status_column($column, $post_id)
{
	if ($column === 'villastatus') {
		$post_status = get_post_status($post_id);
		if ($post_status === 'draft') {
			echo '<span style="color:red;">' . esc_html(__('Draft', 'villa-collective')) . '</span>';
		} else {
			$villastatus = get_post_meta($post_id, 'villastatus', true);
			if ($villastatus) {
				$formatted_status = ucwords(str_replace('_', ' ', $villastatus));
				$color = ($formatted_status === 'Live Online') ? 'green' : 'red';
				echo '<span style="color:' . esc_attr($color) . ';">' . esc_html($formatted_status) . '</span>';
			} else {
				echo esc_html(__('No Status', 'villa-collective'));
			}
		}
	}
}

add_filter('manage_edit-villa-detail_sortable_columns', 'villa_status_sortable_column');
function villa_status_sortable_column($columns)
{
	$columns['villastatus'] = 'villastatus';
	return $columns;
}

add_action('pre_get_posts', 'villa_status_orderby');
function villa_status_orderby($query)
{
	if (!is_admin() || !$query->is_main_query()) return;

	$screen = get_current_screen();
	if ($screen->post_type === 'villa-detail') {
		if ('villastatus' === $query->get('orderby')) {
			$query->set('meta_key', 'villastatus');
			$query->set('orderby', 'meta_value');
		}
	}
}

function custom_rewrite_rules()
{

	// Handle Booking Rewrite Rule
	add_rewrite_rule(
		'^booking/([^/]+)/?$',
		'index.php?post_type=booking&name=$matches[1]',
		'top'
	);

	// Handle wishlish sub pages structure (like /wishlist/ZEXhi9FN/)
	add_rewrite_rule(
		'^wishlist/([^/]+)/?$',
		'index.php?pagename=wishlist&code=$matches[1]',
		'top'
	);

	// Handle general page and subpage structure (like /greece/corfu/)
	add_rewrite_rule(
		'^([^/]+/[^/]+)/?$',
		'index.php?pagename=$matches[1]',
		'top'
	);

	// Collections Rewrite Rule (For taxonomy 'collections' with villa-detail posts)
	add_rewrite_rule(
		'^collections/([^/]+)/?$',
		'index.php?post_type=villa-detail&taxonomy=collections&term=$matches[1]',
		'top'
	);

	// Villa Detail Rewrite Rule (Only for villa-detail, not interfering with collections)
	add_rewrite_rule(
		'^([^/]+)/([^/]+)/?$',
		'index.php?post_type=villa-detail&country=$matches[1]&name=$matches[2]',
		'top'
	);

	// Journal News Rewrite Rule
	add_rewrite_rule(
		'^journal/([^/]+)/([^/]+)/?$',
		'index.php?post_type=journal-news&journal-category=$matches[1]&name=$matches[2]',
		'top'
	);
}
add_action('init', 'custom_rewrite_rules');

// Flush rewrite rules on theme/plugin activation
function flush_rewrite_on_activation()
{
	custom_rewrite_rules();
	flush_rewrite_rules();
}
register_activation_hook(__FILE__, 'flush_rewrite_on_activation');

function custom_flush_rewrite_rules_on_publish($post_id)
{
	// Avoid running on autosave or non-post types
	if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
	if (get_post_type($post_id) !== 'post' && get_post_type($post_id) !== 'page') return;

	// Flush rewrite rules after publishing
	flush_rewrite_rules();
}
add_action('publish_post', 'custom_flush_rewrite_rules_on_publish');
add_action('publish_page', 'custom_flush_rewrite_rules_on_publish');

// Ensure the permalink structure
function custom_rewrite_rule_and_permalink($permalink, $post = null)
{
	if ($post) {

		// Handling custom permalink for 'villa-detail'
		if ($post->post_type == 'villa-detail') {
			$terms = wp_get_post_terms($post->ID, 'country');
			if (!empty($terms) && !is_wp_error($terms)) {
				// Filter child terms (where parent != 0)
				$child_terms = array_filter($terms, function ($term) {
					return $term->parent != 0;
				});

				// If there are any child terms, use the first one
				if (!empty($child_terms)) {
					$child_term = array_shift($child_terms); // Get the first child term
					$permalink = home_url('/' . $child_term->slug . '/' . $post->post_name);
				} else {
					// If no child terms, find the parent term and use its slug
					$parent_term = null;
					foreach ($terms as $term) {
						if ($term->parent == 0) {
							$parent_term = $term;
							break;
						}
					}
					if ($parent_term) {
						$permalink = home_url('/' . $parent_term->slug . '/' . $post->post_name);
					} else {
						// Fallback to just post name if no parent found
						$permalink = home_url('/' . $post->post_name);
					}
				}
			} else {
				// If no terms, fallback to post name without country
				$permalink = home_url('/' . $post->post_name);
			}
		}

		// Handling custom permalink for 'journal-news'
		if ($post->post_type == 'journal-news') {
			$terms = wp_get_post_terms($post->ID, 'journal-category');
			if (!empty($terms) && !is_wp_error($terms)) {
				// Loop through terms and find the first parent term
				$parent_term = null;
				foreach ($terms as $term) {
					if ($term->parent == 0) {
						$parent_term = $term;
						break; // Break after finding the first parent term
					}
				}

				if ($parent_term) {
					$permalink = home_url('/journal/' . $parent_term->slug . '/' . $post->post_name);
				} else {
					// If no parent term found, use the first term available
					$permalink = home_url('/journal/' . $terms[0]->slug . '/' . $post->post_name);
				}
			} else {
				$permalink = home_url('/journal/' . $post->post_name);
			}
		}

		// Handling custom permalink for 'booking'
		if ($post->post_type == 'booking') {
			$permalink = home_url('/booking/' . $post->post_name);
		}
	}

	return $permalink;
}
add_filter('post_type_link', 'custom_rewrite_rule_and_permalink', 10, 2);

// Make permalink editable
function custom_permalink_for_post_editor($permalink, $post)
{
	if (is_object($post) && $post->post_type == 'journal-news') {
		$terms = wp_get_post_terms($post->ID, 'journal-category');
		if (!empty($terms)) {
			$parent_term = null;
			foreach ($terms as $term) {
				if ($term->parent == 0) {
					$parent_term = $term;
					break;
				}
			}
			if ($parent_term) {
				return home_url('/journal/' . $parent_term->slug . '/' . $post->post_name);
			}
		}
	}

	if (is_object($post) && $post->post_type == 'villa-detail') {
		$terms = wp_get_post_terms($post->ID, 'country');
		if (!empty($terms)) {
			$parent_term = null;
			foreach ($terms as $term) {
				if ($term->parent == 0) {
					$parent_term = $term;
					break;
				}
			}
			if ($parent_term) {
				return home_url('/' . $parent_term->slug . '/' . $post->post_name);
			}
		}
	}

	if (is_object($post) && $post->post_type == 'booking') {
		return home_url('/booking/' . $post->post_name);
	}

	// Default permalink if no custom rules match
	return $permalink;
}
add_filter('get_sample_permalink', 'custom_permalink_for_post_editor', 10, 2);

// Remove the final slash (/) on all URLs
remove_action('template_redirect', 'redirect_canonical');
add_filter('user_trailingslashit', 'remove_trailing_slash', 10, 2);
add_filter('term_link', 'remove_trailing_slash_from_term_link', 10, 2);

function remove_trailing_slash($url, $type)
{
	// Check for single posts and pages
	if ('single' === $type || 'page' === $type) {
		return untrailingslashit($url);
	}

	// Check for the homepage (front page)
	if (is_front_page() || is_home()) {
		return untrailingslashit($url);
	}

	// Check for custom taxonomy 'collections' with custom post type 'villa-detail'
	if (is_tax('collections') && 'villa-detail' === get_post_type()) {
		return untrailingslashit($url);
	}

	return $url;
}

// Function to remove trailing slash from term link
function remove_trailing_slash_from_term_link($url, $term)
{
	// Check if the taxonomy is 'collections'
	if ($term->taxonomy === 'collections') {
		return untrailingslashit($url);
	}
	return $url;
}

// Force www in URLs
function force_www_in_urls()
{
	if (WP_SITE_ENV != 'Local') {
		$current_url = $_SERVER['HTTP_HOST'];
		if (strpos($current_url, 'www.') === false) {
			$redirect_url = 'https://www.' . $_SERVER['HTTP_HOST'] . $_SERVER['REQUEST_URI'];
			wp_redirect($redirect_url, 301);
			exit;
		}
	}
}
add_action('template_redirect', 'force_www_in_urls');

// Geneate unique string for Booking
function generateUniqueString()
{
	// Generate a unique string using random alphanumeric characters and hyphens
	$characters = 'abcdefghijklmnopqrstuvwxyz0123456789-';
	$length = 36; // Length for the UUID-like format

	$uniqueString = '';
	for ($i = 0; $i < $length; $i++) {
		// Append a random character from the allowed set
		$uniqueString .= $characters[rand(0, strlen($characters) - 1)];
	}

	// Format the string like UUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
	$formattedString = substr($uniqueString, 0, 8) . '-' .
		substr($uniqueString, 8, 4) . '-' .
		substr($uniqueString, 12, 4) . '-' .
		substr($uniqueString, 16, 4) . '-' .
		substr($uniqueString, 20, 12);

	return $formattedString;
}

// Modify the booking post title
function modify_booking_post_title($title, $post_id)
{
	if (is_admin() && get_post_type($post_id) === 'booking') {
		$booking_reference = get_field('bookingreference', $post_id);
		if ($booking_reference) {
			return 'Booking - ' . $booking_reference;
		}
	}
	return $title;
}
add_filter('the_title', 'modify_booking_post_title', 10, 2);

// Custom title tag for booking post
function custom_title_tag($title)
{
	if (is_singular('booking')) {
		$bookingreference = get_post_meta(get_the_ID(), 'bookingreference', true);
		if ($bookingreference) {
			$title = 'Booking - ' . esc_html($bookingreference) . ' &ndash; Villa Collective';
		}
	}
	return $title;
}
add_filter('pre_get_document_title', 'custom_title_tag');

function update_payment_due_dates($postId, $payment_id, $payment_response)
{
	$value = get_field('paymentduesdates', $postId);
	$PaymentDuesDates  = [];
	$is_security_deposite = false;
	foreach ($value as $sub_key => $sub_value) {
		$PaymentDuesDates[$sub_key]['id'] = $sub_value['id'];
		$PaymentDuesDates[$sub_key]['description'] = $sub_value['description'];
		$PaymentDuesDates[$sub_key]['amount'] = (float) $sub_value['amount'];
		$PaymentDuesDates[$sub_key]['date'] = $sub_value['date'];
		$PaymentDuesDates[$sub_key]['ispayment'] = $sub_value['ispayment'];
		if ($sub_value['id'] == $payment_id) {
			$PaymentDuesDates[$sub_key]['paymentresponse'] = $payment_response;
			if ($sub_value['description'] == "Security Deposit") {
				$is_security_deposite = true;
			}
		} else {
			$PaymentDuesDates[$sub_key]['paymentresponse'] = $sub_value['paymentresponse'];
		}
	}
	if ($is_security_deposite) {
		update_field('security_deposite_response', $payment_response, $postId);
	}
	update_field('paymentduesdates', $PaymentDuesDates, $postId);
}

// Flywire payment response and post API for RES
function payment_response($data)
{
	$postId = get_the_ID();

	$status = $data['status'];
	if (isset($status) && $status == 'active') {
		update_field('payment', true, $postId);
	}

	// Flywire payment response
	$paymentResponse = '';
	foreach ($data as $key => $value) {
		$paymentResponse .= $key . " : " . $value . "\r\n";
	}
	$paymentResponse = rtrim($paymentResponse, "\r\n");
	$post_data = [];
	if (isset($data['conciergeid'])) {
		$ConciergeService = [];
		$post_data['conciergeid'] = base64_decode($data['conciergeid']);
		$conciergeservice_data = get_field('conciergeservice', $postId);
		if ($conciergeservice_data) {
			foreach ($conciergeservice_data as $key => $val) {
				$ConciergeService[$key]['conciergeid'] = $val['conciergeid'];
				$ConciergeService[$key]['description'] = $val['description'];
				$ConciergeService[$key]['conciergedata'] = $val['conciergedata'];
				if (base64_decode($data['conciergeid']) == $val['conciergeid']) {
					$ConciergeService[$key]['paymentresponse'] = $paymentResponse;
				} else {
					$ConciergeService[$key]['paymentresponse'] = $val['paymentresponse'];
				}
			}
			update_field('conciergeservice', $ConciergeService, $postId);
		}
	} else if (trim($data['payment_method']) == "scheduled") {
		update_field('payment_response', $paymentResponse, $postId);
		update_payment_due_dates($postId, $data['payment_id'], $paymentResponse);
	} else {
		update_payment_due_dates($postId, $data['payment_id'], $paymentResponse);
	}

	// Post API Data for RES
	$post_data['PayRefNo'] = $data['reference'];
	$post_data['Status'] = $data['status'];
	$post_data['Amount'] = $data['amount'];
	$post_data['PayerAmount'] = $data['payerAmount'] ?? "";
	$post_data['AmountCurrency'] = $data['payerAmountCurrency'] ?? "";
	$post_data['PayerAmountCurrency'] = $data['payerAmountCurrency'] ?? "";
	$post_data['PaymentMethod'] = $data['payment_method'];
	$post_data['sig'] = $data['sig'] ?? "";
	$post_data['BookingRefNo'] = get_field('bookingreference', $postId);
	$post_data['BookingId'] = get_field('bookingid', $postId);
	$propertyids = get_field('propertyids', $postId);
	if (isset($propertyids[0])) {
		$post_data['VillaId'] = get_field('propertyid', $propertyids[0]);
	} else {
		$post_data['VillaId'] = 0;
	}
	//echo "<pre>"; print_r($post_data); die;

	// Post API for RES
	$post_data = json_encode($post_data);
	$url = "Payment/PaymentStatus";
	if (isset($data['conciergeid'])) {
		//if need then send to api other wise not 
	} else {
		$send_to_res = post_api_call($url, $post_data);
	}
}

// Booking confirm and post API for RES
function booking_confirm()
{
	$postId = $_POST['postId'];
	$BookingId = $_POST['BookingId'];
	$BookingRefNo = $_POST['BookingRefNo'];
	$VillaId = $_POST['VillaId'];

	update_field('confirm_booking', true, $postId);

	// Post API for RES
	$post_data['bookingid'] = $BookingId;
	$post_data['bookingreference'] = $BookingRefNo;
	$post_data['confirm_booking'] = true;
	$post_data['reject_reason'] = '';
	//echo "<pre>"; print_r($post_data); die;

	$post_data = json_encode($post_data);
	$url = "Payment/ConfirmBooking";
	$send_to_res = post_api_call($url, $post_data);

	echo json_encode(['message' => 'Booking Confirmed']);
	die();
}
add_action('wp_ajax_nopriv_booking_confirm', 'booking_confirm');
add_action('wp_ajax_booking_confirm', 'booking_confirm');

// Booking rejection with reason and post API for RES
function booking_rejection()
{
	$postId = $_POST['postId'];
	$BookingId = $_POST['BookingId'];
	$BookingRefNo = $_POST['BookingRefNo'];
	$VillaId = $_POST['VillaId'];
	$reject_reason = $_POST['reject_reason'];

	update_field('reject_reason', $reject_reason, $postId);
	update_field('confirm_booking', false, $postId);

	// Post API for RES
	$post_data['bookingid'] = $BookingId;
	$post_data['bookingreference'] = $BookingRefNo;
	$post_data['confirm_booking'] = false;
	$post_data['reject_reason'] = $reject_reason;
	//echo "<pre>"; print_r($post_data); die;

	$post_data = json_encode($post_data);
	$url = "Payment/ConfirmBooking";
	$send_to_res = post_api_call($url, $post_data);

	echo json_encode(['message' => 'Booking Rejected']);
	die();
}
add_action('wp_ajax_nopriv_booking_rejection', 'booking_rejection');
add_action('wp_ajax_booking_rejection', 'booking_rejection');

add_action('init', 'custom_child_page_rewrite_rules');
function custom_child_page_rewrite_rules()
{
	$args = array(
		'post_type' => 'page',
		'post_parent__not_in' => array(0),
		'posts_per_page' => -1,
	);
	$child_pages = get_posts($args);

	foreach ($child_pages as $page) {
		$slug = basename(get_permalink($page->ID));
		add_rewrite_rule(
			'^' . $slug . '/?$',
			'index.php?page_id=' . $page->ID,
			'top'
		);
	}
}

// Flush rewrite rules when the theme is activated or when needed
add_action('after_switch_theme', 'flush_rewrite_rules_on_theme_switch');
function flush_rewrite_rules_on_theme_switch()
{
	flush_rewrite_rules();
}

add_action('template_redirect', 'redirect_old_child_urls');
function redirect_old_child_urls()
{
	if (is_page()) {
		global $post;
		if ($post->post_parent) {
			$parent_slug = get_post_field('post_name', $post->post_parent);
			$current_slug = $post->post_name;
			$request_uri = trim($_SERVER['REQUEST_URI'], '/');
			if (strpos($request_uri, $parent_slug . '/' . $current_slug) !== false) {
				wp_redirect(home_url($current_slug), 301);
				exit;
			}
		}
	}
}

function ajax_request_manual_invoice()
{
	$status = false;
	$message = "";

	$post_data = json_encode($_POST['data']);

	$url = "Properties/ManualInvoiceRequest";
	$response_data = post_api_call($url, $post_data);

	if (isset($response_data->Status) && $response_data->Status == 1) {
		$status = true;
		$message = "Request manual invoice has been sent successfully.";
	} else {
		$message = $response_data->Data;
	}

	echo json_encode(['msg' => $message, 'status' => $status]);
	die();
}
add_action('wp_ajax_nopriv_ajax_request_manual_invoice', 'ajax_request_manual_invoice');
add_action('wp_ajax_ajax_request_manual_invoice', 'ajax_request_manual_invoice');


function write_json_to_log($data)
{
	$log_file = WP_CONTENT_DIR . '/my-custom-log.json';

	// Convert data to JSON
	$json_data = json_encode($data, JSON_PRETTY_PRINT);

	// Check if file exists, create if not
	if (!file_exists($log_file)) {
		file_put_contents($log_file, "[" . PHP_EOL);
	} else {
		// Remove last bracket
		$content = file_get_contents($log_file);
		$content = rtrim($content);
		$content = substr($content, 0, strrpos($content, ']'));
		file_put_contents($log_file, $content . ',' . PHP_EOL);
	}

	// Append JSON data and close the array
	file_put_contents($log_file, $json_data . PHP_EOL . "]", FILE_APPEND);
}

add_action('template_redirect', function () {
	ob_start(function ($buffer) {
		// Remove the <style id="rocket-lazyrender-inline-css"> block
		return preg_replace('/<style id="rocket-lazyrender-inline-css".*?<\/style>/s', '', $buffer);
	});
});

/* Cookie yes plugin stores its banner templates in the wordpress options table "cky_banner_template", this function hooks into that option and strips out heading markup affecting structure sitewide (role="heading" aria-level="1")  */
add_filter('option_cky_banner_template', function ($templates) {
	foreach ($templates as $lang => $data) {
		if (! empty($data['html'])) {
			// strip any role="heading" aria-level="1"
			$templates[$lang]['html'] = preg_replace(
				'/\s*role="heading"\s*aria-level="1"/i',
				'',
				$data['html']
			);
		}
	}
	return $templates;
});

/* PHP Villa list query functions  start here */

/**
 * Prepares the exact filter & sort parameters like AJAX handler
 */
function get_villa_list_query_args()
{
	global $post;

	$page_name = get_the_title($post->ID);
	$slug      = $post->post_name;
	if ($page_name !== 'Destinations') {
		if (is_page() && $post->post_parent) {
			$parent = get_the_title($post->post_parent);
			$term   = get_term_by('name', $parent, 'country');
		} else {
			$term   = get_term_by('name', $page_name, 'country');
		}
		$c_id = $term ? intval($term->term_id) : 0;
	} else {
		$c_id = 0;
	}

	$f_id = isset($_GET['f_id'])
		? intval(encode_id($_GET['f_id'], 'decode'))
		: 0;

	// Price cap
	$hard_cap_slugs = ['corfu', 'greece', 'france', 'italy', 'morocco', 'spain', 'kenya', 'destinations'];
	if (in_array($slug, $hard_cap_slugs, true)) {
		$max_price = 30000;
	} else {
		$max_price = custom_get_min_max_price('max');
	}

	// Sort defaults (Price high to low)
	$sort_by    = 2;
	$sort_order = in_array($sort_by, [1, 3], true) ? 'ASC' : 'DESC';
	$sort_key   = in_array($sort_by, [1, 2], true) ? 'maxprice' : 'bedrooms';

	// tax_query
	$tax = ['relation' => 'AND'];

	if ($c_id) {
		$tax[] = [
			'taxonomy' => 'country',
			'field'    => 'term_id',
			'terms'    => $c_id,
		];
	}

	// Region filter
	$region_ids = [];
	if (! empty($_POST['regions_ids']) && is_array($_POST['regions_ids'])) {
		$region_ids = array_map('intval', $_POST['regions_ids']);
	} elseif ($page_name !== 'Destinations' && is_page() && $post->post_parent) {
		$reg = get_term_by('slug', $slug, 'country');
		if ($reg) {
			$region_ids = [intval($reg->term_id)];
		}
	}
	if ($region_ids) {
		$tax[] = [
			'taxonomy' => 'country',
			'field'    => 'term_id',
			'terms'    => $region_ids,
			'operator' => 'IN',
		];
	}

	// Collections 
	$collection_ids = ! empty($_POST['CollectionIds']) && is_array($_POST['CollectionIds'])
		? array_map('intval', $_POST['CollectionIds'])
		: [];
	if ($collection_ids) {
		$tax[] = [
			'taxonomy' => 'collections',
			'field'    => 'term_id',
			'terms'    => $collection_ids,
			'operator' => 'IN',
		];
	}

	$keyfeatures = [];
	if (! empty($_POST['KeyFeatures']) && is_array($_POST['KeyFeatures'])) {
		$keyfeatures = array_map('intval', $_POST['KeyFeatures']);
	} elseif ($f_id) {
		$keyfeatures = [$f_id];
	}
	if ($keyfeatures) {
		$tax[] = [
			'taxonomy' => 'key-feature',
			'field'    => 'term_id',
			'terms'    => $keyfeatures,
			'operator' => 'IN',
		];
	}

	//  meta_query
	$meta = ['relation' => 'AND'];

	if ($max_price) {
		$meta[] = [
			'key'     => 'maxprice',
			'value'   => $max_price,
			'compare' => '<=',
			'type'    => 'NUMERIC',
		];
	}

	// Bedrooms (range)
	$minbed = isset($_POST['MinBed']) ? intval($_POST['MinBed']) : 0;
	$maxbed = isset($_POST['MaxBed']) ? intval($_POST['MaxBed']) : 0;
	if ($minbed && $maxbed) {
		$meta[] = [
			'relation' => 'AND',
			[
				'key'     => 'bedrooms',
				'value'   => $minbed,
				'compare' => '>=',
				'type'    => 'NUMERIC',
			],
			[
				'key'     => 'bedrooms',
				'value'   => $maxbed,
				'compare' => '<=',
				'type'    => 'NUMERIC',
			],
		];
	} elseif ($minbed) {
		$meta[] = [
			'key'     => 'bedrooms',
			'value'   => $minbed,
			'compare' => '>=',
			'type'    => 'NUMERIC',
		];
	}

	// Exact bedrooms
	$bedroom = isset($_POST['bedroom']) ? intval($_POST['bedroom']) : 0;
	if ($bedroom) {
		$meta[] = [
			'key'     => 'bedrooms',
			'value'   => $bedroom,
			'compare' => '=',
			'type'    => 'NUMERIC',
		];
	}

	// Bathrooms
	$bathroom = isset($_POST['bathroom']) ? intval($_POST['bathroom']) : 0;
	if ($bathroom) {
		$meta[] = [
			'key'     => 'bathroom',
			'value'   => $bathroom,
			'compare' => '=',
			'type'    => 'NUMERIC',
		];
	}

	// Guests
	$guest = isset($_POST['guest']) ? intval($_POST['guest']) : 0;
	if ($guest) {
		$meta[] = [
			'key'     => 'guest',
			'value'   => $guest,
			'compare' => '=',
			'type'    => 'NUMERIC',
		];
	}

	// Exclude live_offline
	$meta[] = [
		'key'     => 'villastatus',
		'value'   => 'live_offline',
		'compare' => '!=',
	];

	return compact('tax', 'meta', 'sort_key', 'sort_order');
}

/*
 Retrieves the total count and the specific page of villas using the filters & sorting built by get_villa_list_query_args(), so the initial server render matches what the AJAX calls would fetch.
 */
function get_villa_list_data($page = 1)
{
	$args     = get_villa_list_query_args();
	$per_page = 12;
	$offset   = ($page - 1) * $per_page;

	// Count
	$count_q = new WP_Query([
		'post_type'   => 'villa-detail',
		'post_status' => 'publish',
		'tax_query'   => $args['tax'],
		'meta_query'  => $args['meta'],
		'fields'      => 'ids',
		'distinct'    => true,
	]);
	$total = $count_q->found_posts;
	wp_reset_postdata();

	// Page data
	$list_q = new WP_Query([
		'post_type'      => 'villa-detail',
		'posts_per_page' => $per_page,
		'offset'         => $offset,
		'orderby'        => 'meta_value_num',
		'meta_key'       => $args['sort_key'],
		'order'          => $args['sort_order'],
		'post_status'    => 'publish',
		'tax_query'      => $args['tax'],
		'meta_query'     => $args['meta'],
		'fields'         => 'all',
		'distinct'       => true,
	]);
	$posts = $list_q->posts;
	wp_reset_postdata();

	return compact('total', 'posts');
}

/* Renders the first page of villas plus the map/list toggle UI on initial load, using the same filtering & sorting logic as the AJAX calls.
*/
function render_initial_villa_list()
{
	$data = get_villa_list_data(1);

	// Map + count
	echo '<div class="col-6"><div class="map-view">'
		. '<a href="javascript:;" data-target="section-map-view">'
		. '<img src="' . get_stylesheet_directory_uri() . '/assets/images/map-view-icon.svg"'
		. ' alt="Map View" class="img-fluid">Map View</a>'
		. '<a href="javascript:;" data-target="section-list-view" style="display:none;">'
		. '<img src="' . get_stylesheet_directory_uri() . '/assets/images/list-view-icon.svg"'
		. ' alt="List View" class="img-fluid">List</a>'
		. '</div></div>';
	echo '<div class="col-6"><div class="showing">'
		. esc_html($data['total']) . ' VILLAS</div></div>';

	// Villas
	echo '<div id="section-list-view" class="col-1g-12"><div class="row">';
	if ($data['posts']) {
		$seen = [];
		foreach ($data['posts'] as $p) {
			if (in_array($p->ID, $seen, true)) continue;
			$seen[] = $p->ID;
			echo render_initial_villa_item($p->ID);
		}
	} else {
		echo 'No more villas';
	}
	echo '</div></div>';
}

/* Render the initial "Load More" pagination button.*/
function render_initial_villa_pagination()
{
	$data = get_villa_list_data(1);
	if ($data['total'] > 12) {
		$next = 2;
		echo '<div class="col-lg-12 ' . $data['total'] . '">'
			. '<div class="pagination-btn">'
			. '<input type="hidden" id="current_page" value="1">'
			. '<button type="button" class="next-btn" id="next-page" data-page="' . $next . '">'
			. 'Load More</button>'
			. '</div></div>';
	}
}

/* Render single villa item. Mirrors get_villa_info_element(), adapted for initial server load. */
function render_initial_villa_item($post_id)
{
	$fav_villa       = isset($_COOKIE['villa_fav']) ? explode(',', $_COOKIE['villa_fav']) : [];
	$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
	$villa_url       = get_permalink($post_id);
	$state           = get_field('state', $post_id);
	$country         = get_field('country', $post_id);
	$curr_display    = get_field('currencysymboldisplay', $post_id);
	$ispoa           = get_field('ispoaprice', $post_id);
	$csymbol         = get_field('currencysymbol', $post_id);
	$minprice        = get_field('minprice', $post_id);
	$maxprice        = get_field('maxprice', $post_id);
	$maxprice        = $maxprice ? ' - ' . price_format($maxprice) : '';
	$prtype          = get_field('pricetype', $post_id);
	$prtype          = $prtype ? ' / ' . $prtype : '';
	$guest           = get_field('guest', $post_id);
	$guest_str       = $guest > 1 ? 'GUESTS' : 'GUEST';
	$additional      = get_field('additionalguest', $post_id);
	$addguest        = $additional ? '+' . $additional : '';
	$bedrooms        = get_field('bedrooms', $post_id);
	$bed_str         = $bedrooms > 1 ? 'BEDROOMS' : 'BEDROOM';
	$bathrooms       = get_field('bathroom', $post_id);
	$bath_str        = $bathrooms > 1 ? 'BATHROOMS' : 'BATHROOM';

	// Collect images
	$slider_imgs = [];
	if ($feat = get_the_post_thumbnail_url($post_id)) {
		$slider_imgs[] = $feat;
	}
	foreach ((array) get_field('exteriorimages', $post_id) as $img) {
		$slider_imgs[] = $img;
	}
	foreach ((array) get_field('interiorimages', $post_id) as $img) {
		$slider_imgs[] = $img;
	}
	if (empty($slider_imgs)) {
		$slider_imgs[] = $image_not_found;
	}

	// Price string
	$villa_price = $ispoa
		? 'Price on request'
		: ($curr_display
			? price_format($minprice) . $maxprice . $csymbol . $prtype
			: $csymbol . price_format($minprice) . $maxprice . $prtype
		);

	// Heart icon
	$heart = in_array($post_id, $fav_villa)
		? 'fa fa-heart'
		: 'fa-regular fa-heart';

	// Build output
	$out  = '<div class="col-sm-6 col-md-6 col-lg-6 col-xl-6 col-xxl-4 mb-48 animate__animated animate__slideInUp">';
	$out .= '<div class="villa-collective-sure-box">';

	// Slider
	$out .= '<div class="villa-collective-sure-slider">';
	$out .= '<div class="villa-collective-info">'
		.   category_bedge($post_id)
		.   '<span class="add_favourite" data-type="0" data-villa_id="' . esc_attr($post_id) . '">'
		.     '<i class="' . esc_attr($heart) . '"></i>'
		.   '</span>'
		. '</div>';
	$out .= '<div class="carousel-wrap">';
	$out .= '<div class="villa-collective-slider owl-carousel owl-theme" style="display:block;">';
	foreach ($slider_imgs as $i => $img_url) {
		$style = $i > 0 ? ' style="display:none;"' : '';
		$out .= '<div class="item"' . $style . '>';
		$out .= '<a href="' . esc_url($villa_url) . '" target="_blank">';
		$out .= '<div class="villa-collective-sure-box-img-slider no-lazyload"'
			.   ' style="background-image:url(' . esc_url($img_url) . ');">'
			. '</div>';
		$out .= '</a></div>';
	}
	$out .= '</div></div></div>';

	// Content
	$out .= '<a href="' . esc_url($villa_url) . '" target="_blank">';
	$out .= '<div class="villa-collective-cnt">';
	$out .= '<span>' . esc_html("$state, $country") . '</span>';
	$out .= '<div class="villa-collective-head"><h3>'
		. esc_html(get_the_title($post_id))
		. '</h3></div>';
	$out .= '<div class="mt-auto"><div class="amount">'
		. esc_html($villa_price)
		. '</div>';
	$out .= '<div class="row justify-content-center">';
	$out .= '<div class="col-4"><div class="villa-collective-amenity">'
		. '<span class="h6">' . esc_html($guest . $addguest) . '</span>'
		. '<span>' . esc_html($guest_str) . '</span>'
		. '</div></div>';
	$out .= '<div class="col-4"><div class="villa-collective-amenity">'
		. '<span class="h6">' . esc_html($bedrooms) . '</span>'
		. '<span>' . esc_html($bed_str) . '</span>'
		. '</div></div>';
	$out .= '<div class="col-4"><div class="villa-collective-amenity">'
		. '<span class="h6">' . esc_html($bathrooms) . '</span>'
		. '<span>' . esc_html($bath_str) . '</span>'
		. '</div></div>';
	$out .= '</div></div>';
	$out .= '</div></a>';
	$out .= '</div></div>';

	return $out;
}


function vc_enquire_button($villa_id = 0, $classes = 'thm-btn-3', $label = 'Enquire')
{
	$url = get_permalink(get_page_by_path('enquiry'));
	$villa_id = absint($villa_id);

	if (! $villa_id) {
		return sprintf(
			'<a href="%1$s" class="%2$s">%3$s</a>',
			esc_url($url),
			esc_attr($classes),
			esc_html($label)
		);
	}

	ob_start(); ?>
	<form action="<?php echo esc_url($url); ?>" method="post" class="enquire-form">
		<?php wp_nonce_field('enquire_villa', 'enquire_nonce'); ?>
		<input type="hidden" name="villa_id" value="<?php echo esc_attr($villa_id); ?>">
		<button type="submit" class="<?php echo esc_attr($classes); ?>">
			<?php echo esc_html($label); ?>
		</button>
	</form>
<?php
	return ob_get_clean();
}

add_action('wp_ajax_nopriv_cardpayment_response', 'cardpayment_response');
add_action('wp_ajax_cardpayment_response', 'cardpayment_response');

function cardpayment_response()
{

	$data = $_POST['data'];
	$postId = $data['post_id'];

	$status = $data['status'];
	if (isset($status) && ($status == 'active' || $status == "success" || $status == "pending")) {
		update_field('payment', true, $postId);
	}

	// Flywire payment response
	$paymentResponse = '';
	foreach ($data as $key => $value) {
		$paymentResponse .= $key . " : " . $value . "\r\n";
	}
	$paymentResponse = rtrim($paymentResponse, "\r\n");
	update_field('payment_response', $paymentResponse, $postId);
	update_payment_due_dates($postId, $data['payment_id'], $paymentResponse);
	// Post API Data for RES
	$post_data['reference'] = $data['reference'] ?? "";
	$post_data['status'] = $data['status'];
	$post_data['amount'] = $data['amount'] ?? 0;
	$post_data['paymentMethod'] = $data['paymentMethod'] ?? "";
	$post_data['bankTransferDueDate'] = $data['bankTransferDueDate'] ?? "";
	$post_data['sig'] = $data['sig'] ?? "";
	$post_data['amountCurrency'] = $data['amountCurrency'] ?? "";
	$post_data['payerAmount'] = $data['payerAmount'] ?? 0;
	$post_data['payerAmountCurrency'] = $data['payerAmountCurrency'] ?? "";
	$post_data['token'] = $data['token'] ?? "";
	$post_data['digits'] = $data['digits'] ?? "";
	$post_data['expirationMonth'] = $data['expirationMonth'] ?? "";
	$post_data['expirationYear'] = $data['expirationYear'] ?? "";
	$post_data['type'] = $data['type'] ?? "";
	$post_data['brand'] = $data['brand'] ?? "";
	$post_data['bookingRefNo'] = get_field('bookingreference', $postId);
	$post_data['BookingId'] = get_field('bookingid', $postId);
	$propertyids = get_field('propertyids', $postId);
	if (isset($propertyids[0])) {
		$post_data['VillaId'] = get_field('propertyid', $propertyids[0]);
	} else {
		$post_data['VillaId'] = 0;
	}

	// Post API for RES
	$post_data = json_encode($post_data);
	$url = "Payment/TokenisePaymentStatus";
	$send_to_res = post_api_call($url, $post_data);
}

/* filtering parents from destinations in canonicals and sitemap*/
add_filter('wpseo_canonical', 'vc_canonical_match_visible_url');
function vc_canonical_match_visible_url($canonical)
{
	// Only for pages.
	if (! is_page()) {
		return $canonical;
	}

	// Visible path (no query string).
	$path = trim(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), '/');

	// Apply the same trailing-slash logic WP is using elsewhere.
	$visible_url = user_trailingslashit(home_url($path), 'page');

	// If Yoast already has it, leave it alone.
	if (untrailingslashit($canonical) === untrailingslashit($visible_url)) {
		return $canonical;
	}
	return $visible_url;
}

add_filter('wpseo_sitemap_entry', 'vc_fix_sitemap_loc', 10, 3);
function vc_fix_sitemap_loc($url, $type, $post)
{

	// Yoast uses 'post' for post-type sitemaps.
	if ($type !== 'post' || $post->post_type !== 'page') {
		return $url;
	}

	if (! $post->post_parent) {
		return $url;
	}

	$visible          = user_trailingslashit(home_url($post->post_name), 'page');
	$url['loc']       = $visible;
	$url['canonical'] = $visible;

	return $url;
}

// Yoast SEO: Replace content with ACF field ONLY for a specific post type
add_filter('wpseo_pre_analysis_post_content', function ($content) {
	global $post;

	// Only for 'villa-detail'
	if ($post && $post->post_type === 'villa-detail') {

		// Get your ACF field value
		$acf_content = get_field('overview', $post->ID);

		// If field has value, replace default content
		if ($acf_content) {
			return $acf_content;
		}
	}

	// Fallback: default WP editor content
	return $content;
});



add_action('wp_ajax_nopriv_personalinfo_add', 'personalinfo_add');
add_action('wp_ajax_personalinfo_add', 'personalinfo_add');

function personalinfo_add()
{

	$data = $_POST;
	$postId = $data['postId'];
	$service = (strtolower($data['service']) == "yes") ? true : false;
	$conciergeid = ($data['conciergeid'] != "") ? $data['conciergeid'] : 0;

	$personal_info[] = [
		'title' => $data['title'],
		'firstname' => $data['first_name'],
		'lastname' => $data['last_name'],
		'streetaddress' => $data['address'],
		'citytown' => $data['city'],
		'postalcode' => $data['postalcode'],
		'country' => [
			[
				'countryid' => "",
				'countryname' => $data['country'],
				'countrycode' => $data['country_phone_code'],
			]
		],
		'emailaddress' => $data['email'],
		'phonenumber' => $data['phone'],
		'otherphone' => $data['other_phone'],
	];

	$additional_info[] = [
		'title' => $data['title2'],
		'firstname' => $data['first_name2'],
		'lastname' => $data['last_name2'],
		'streetaddress' => $data['address2'],
		'citytown' => $data['city2'],
		'postalcode' => $data['postalcode2'],
		'country' => [
			[
				'countryid' => "",
				'countryname' => $data['country2'],
				'countrycode' => $data['country_phone_code2'],
			]
		],
		'emailaddress' => $data['email2'],
		'phonenumber' => $data['phone2'],
		'otherphone' => $data['other_phone2'],
	];

	update_field('personalinfo', $personal_info, $postId);
	update_field('additionalinfo', $additional_info, $postId);
	update_field('signature_service', $service, $postId);

	$PersonalInfo = [];
	$PersonalInfo["Title"] = $data['title'];
	$PersonalInfo["FirstName"] = $data['first_name'];
	$PersonalInfo["LastName"] = $data['last_name'];
	$PersonalInfo["AddressLine1"] = $data['address'];
	$PersonalInfo["Email"] = $data['email'];
	$PersonalInfo["MobileNo"] = $data['phone'];
	$PersonalInfo["CountryCode"] = $data['country_phone_code'];
	$PersonalInfo["Country"] = $data['country'];
	$PersonalInfo["Town"] = $data['city'];
	$PersonalInfo["PostCode"] = $data['postalcode'];
	$PersonalInfo["BookingId"] = $data['BookingId'];
	$PersonalInfo["BookingRefNo"] = $data['BookingRefNo'];
	$PersonalInfo["OtherMobileNo"] = $data['other_phone'];
	$PersonalInfo["IsAdditionalInfo"] = isset($data['another_person']) ? true : false;
	$PersonalInfo["IsConciergeService"] = $service;
	$PersonalInfo["ConciergeId"] = $conciergeid;
	$PersonalInfo["ConciergeDescription"] = "I would like to know more about the Signature Service.";

	$AdditionalInfo = [];
	$AdditionalInfo["Title"] = $data['title2'];
	$AdditionalInfo["FirstName"] = $data['first_name2'];
	$AdditionalInfo["LastName"] = $data['last_name2'];
	$AdditionalInfo["AddressLine1"] = $data['address2'];
	$AdditionalInfo["Email"] = $data['email2'];
	$AdditionalInfo["MobileNo"] = $data['phone2'];
	$AdditionalInfo["CountryCode"] = $data['country_phone_code2'];
	$AdditionalInfo["Country"] = $data['country2'];
	$AdditionalInfo["Town"] = $data['city2'];
	$AdditionalInfo["PostCode"] = $data['postalcode2'];
	$AdditionalInfo["OtherMobileNo"] = $data['other_phone2'];

	$send_data_api = json_encode(["PersonalInfo" => $PersonalInfo, "AdditionalInfo" => $AdditionalInfo]);
	$url = "Payment/SaveCheckoutInfo";
	$send_to_res = post_api_call($url, $send_data_api);
}

function get_country_code($contry_name)
{
	$country_code = ["United Kingdom" => "GB", "United States" => "US", "Australia" => "AU", "Afghanistan" => "AF", "Albania" => "AL", "Algeria" => "DZ", "American Samoa" => "AS", "Andorra" => "AD", "Angola" => "AO", "Anguilla" => "AI", "Antarctica" => "AQ", "Antigua and Barbuda" => "AG", "Argentina" => "AR", "Armenia" => "AM", "Aruba" => "AW", "Austria" => "AT", "Azerbaijan" => "AZ", "Bahamas" => "BS", "Bahrain" => "BH", "Bangladesh" => "BD", "Barbados" => "BB", "Belarus" => "BY", "Belgium" => "BE", "Belize" => "BZ", "Benin" => "BJ", "Bermuda" => "BM", "Bhutan" => "BT", "Bolivia" => "BO", "Bosnia and Herzegovina" => "BA", "Botswana" => "BW", "Bouvet Island" => "BV", "Brazil" => "BR", "British Antarctic Territory" => "BQ", "British Indian Ocean Territory" => "IO", "British Virgin Islands" => "VG", "Brunei" => "BN", "Bulgaria" => "BG", "Burkina Faso" => "BF", "Burundi" => "BI", "Cambodia" => "KH", "Cameroon" => "CM", "Canada" => "CA", "Canton and Enderbury Islands" => "CT", "Cape Verde" => "CV", "Cayman Islands" => "KY", "Central African Republic" => "CF", "Chad" => "TD", "Chile" => "CL", "China" => "CN", "Christmas Island" => "CX", "Cocos [Keeling] Islands" => "CC", "Colombia" => "CO", "Comoros" => "KM", "Congo - Brazzaville" => "CG", "Congo - Kinshasa" => "CD", "Cook Islands" => "CK", "Costa Rica" => "CR", "Croatia" => "HR", "Cuba" => "CU", "Cyprus" => "CY", "Czech Republic" => "CZ", "Côte d’Ivoire" => "CI", "Denmark" => "DK", "Djibouti" => "DJ", "Dominica" => "DM", "Dominican Republic" => "DO", "Dronning Maud Land" => "NQ", "East Germany" => "DD", "Ecuador" => "EC", "Egypt" => "EG", "El Salvador" => "SV", "Equatorial Guinea" => "GQ", "Eritrea" => "ER", "Estonia" => "EE", "Ethiopia" => "ET", "Falkland Islands" => "FK", "Faroe Islands" => "FO", "Fiji" => "FJ", "Finland" => "FI", "France" => "FR", "French Guiana" => "GF", "French Polynesia" => "PF", "French Southern Territories" => "TF", "French Southern and Antarctic Territories" => "FQ", "Gabon" => "GA", "Gambia" => "GM", "Georgia" => "GE", "Germany" => "DE", "Ghana" => "GH", "Gibraltar" => "GI", "Greece" => "GR", "Greenland" => "GL", "Grenada" => "GD", "Guadeloupe" => "GP", "Guam" => "GU", "Guatemala" => "GT", "Guernsey" => "GG", "Guinea" => "GN", "Guinea-Bissau" => "GW", "Guyana" => "GY", "Haiti" => "HT", "Heard Island and McDonald Islands" => "HM", "Honduras" => "HN", "Hong Kong SAR China" => "HK", "Hungary" => "HU", "Iceland" => "IS", "India" => "IN", "Indonesia" => "ID", "Iran" => "IR", "Iraq" => "IQ", "Ireland" => "IE", "Isle of Man" => "IM", "Israel" => "IL", "Italy" => "IT", "Jamaica" => "JM", "Japan" => "JP", "Jersey" => "JE", "Johnston Island" => "JT", "Jordan" => "JO", "Kazakhstan" => "KZ", "Kenya" => "KE", "Kiribati" => "KI", "Kuwait" => "KW", "Kyrgyzstan" => "KG", "Laos" => "LA", "Latvia" => "LV", "Lebanon" => "LB", "Lesotho" => "LS", "Liberia" => "LR", "Libya" => "LY", "Liechtenstein" => "LI", "Lithuania" => "LT", "Luxembourg" => "LU", "Macau SAR China" => "MO", "Macedonia" => "MK", "Madagascar" => "MG", "Malawi" => "MW", "Malaysia" => "MY", "Maldives" => "MV", "Mali" => "ML", "Malta" => "MT", "Marshall Islands" => "MH", "Martinique" => "MQ", "Mauritania" => "MR", "Mauritius" => "MU", "Mayotte" => "YT", "Metropolitan France" => "FX", "Mexico" => "MX", "Micronesia" => "FM", "Midway Islands" => "MI", "Moldova" => "MD", "Monaco" => "MC", "Mongolia" => "MN", "Montenegro" => "ME", "Montserrat" => "MS", "Morocco" => "MA", "Mozambique" => "MZ", "Myanmar [Burma]" => "MM", "Namibia" => "NA", "Nauru" => "NR", "Nepal" => "NP", "Netherlands" => "NL", "Netherlands Antilles" => "AN", "Neutral Zone" => "NT", "New Caledonia" => "NC", "New Zealand" => "NZ", "Nicaragua" => "NI", "Niger" => "NE", "Nigeria" => "NG", "Niue" => "NU", "Norfolk Island" => "NF", "North Korea" => "KP", "North Vietnam" => "VD", "Northern Mariana Islands" => "MP", "Norway" => "NO", "Oman" => "OM", "Pacific Islands Trust Territory" => "PC", "Pakistan" => "PK", "Palau" => "PW", "Palestinian Territories" => "PS", "Panama" => "PA", "Panama Canal Zone" => "PZ", "Papua New Guinea" => "PG", "Paraguay" => "PY", "People's Democratic Republic of Yemen" => "YD", "Peru" => "PE", "Philippines" => "PH", "Pitcairn Islands" => "PN", "Poland" => "PL", "Portugal" => "PT", "Puerto Rico" => "PR", "Qatar" => "QA", "Romania" => "RO", "Russia" => "RU", "Rwanda" => "RW", "Réunion" => "RE", "Saint Barthélemy" => "BL", "Saint Helena" => "SH", "Saint Kitts and Nevis" => "KN", "Saint Lucia" => "LC", "Saint Martin" => "MF", "Saint Pierre and Miquelon" => "PM", "Saint Vincent and the Grenadines" => "VC", "Samoa" => "WS", "San Marino" => "SM", "Saudi Arabia" => "SA", "Senegal" => "SN", "Serbia" => "RS", "Serbia and Montenegro" => "CS", "Seychelles" => "SC", "Sierra Leone" => "SL", "Singapore" => "SG", "Slovakia" => "SK", "Slovenia" => "SI", "Solomon Islands" => "SB", "Somalia" => "SO", "South Africa" => "ZA", "South Georgia and the South Sandwich Islands" => "GS", "South Korea" => "KR", "Spain" => "ES", "Sri Lanka" => "LK", "Sudan" => "SD", "Suriname" => "SR", "Svalbard and Jan Mayen" => "SJ", "Swaziland" => "SZ", "Sweden" => "SE", "Switzerland" => "CH", "Syria" => "SY", "São Tomé and Príncipe" => "ST", "Taiwan" => "TW", "Tajikistan" => "TJ", "Tanzania" => "TZ", "Thailand" => "TH", "Timor-Leste" => "TL", "Togo" => "TG", "Tokelau" => "TK", "Tonga" => "TO", "Trinidad and Tobago" => "TT", "Tunisia" => "TN", "Turkey" => "TR", "Turkmenistan" => "TM", "Turks and Caicos Islands" => "TC", "Tuvalu" => "TV", "U.S. Minor Outlying Islands" => "UM", "U.S. Miscellaneous Pacific Islands" => "PU", "U.S. Virgin Islands" => "VI", "Uganda" => "UG", "Ukraine" => "UA", "Union of Soviet Socialist Republics" => "SU", "United Arab Emirates" => "AE", "Unknown or Invalid Region" => "ZZ", "Uruguay" => "UY", "Uzbekistan" => "UZ", "Vanuatu" => "VU", "Vatican City" => "VA", "Venezuela" => "VE", "Vietnam" => "VN", "Wake Island" => "WK", "Wallis and Futuna" => "WF", "Western Sahara" => "EH", "Yemen" => "YE", "Zambia" => "ZM", "Zimbabwe" => "ZW"];
	return $country_code["$contry_name"] ?? "";
}

function get_countries()
{
	return ["+44" => "United Kingdom", "+1" => "United States", "+61" => "Australia", "+93" => "Afghanistan", "+355" => "Albania", "+213" => "Algeria", "+376" => "Andorra", "+244" => "Angola", "+54" => "Argentina", "+374" => "Armenia", "+43" => "Austria", "+994" => "Azerbaijan", "+973" => "Bahrain", "+880" => "Bangladesh", "+375" => "Belarus", "+32" => "Belgium", "+975" => "Bhutan", "+387" => "Bosnia and Herzegovina", "+55" => "Brazil", "+359" => "Bulgaria", "+855" => "Cambodia", "+237" => "Cameroon", "+56" => "Chile", "+86" => "China", "+57" => "Colombia", "+385" => "Croatia", "+357" => "Cyprus", "+420" => "Czech Republic", "+45" => "Denmark", "+20" => "Egypt", "+372" => "Estonia", "+358" => "Finland", "+33" => "France", "+49" => "Germany", "+30" => "Greece", "+852" => "Hong Kong", "+36" => "Hungary", "+354" => "Iceland", "+91" => "India", "+62" => "Indonesia", "+98" => "Iran", "+964" => "Iraq", "+353" => "Ireland", "+972" => "Israel", "+39" => "Italy", "+81" => "Japan", "+962" => "Jordan", "+7" => "Kazakhstan / Russia", "+254" => "Kenya", "+965" => "Kuwait", "+996" => "Kyrgyzstan", "+856" => "Laos", "+371" => "Latvia", "+961" => "Lebanon", "+370" => "Lithuania", "+352" => "Luxembourg", "+60" => "Malaysia", "+960" => "Maldives", "+52" => "Mexico", "+373" => "Moldova", "+377" => "Monaco", "+976" => "Mongolia", "+212" => "Morocco", "+95" => "Myanmar", "+977" => "Nepal", "+31" => "Netherlands", "+64" => "New Zealand", "+234" => "Nigeria", "+850" => "North Korea", "+47" => "Norway", "+968" => "Oman", "+92" => "Pakistan", "+63" => "Philippines", "+48" => "Poland", "+351" => "Portugal", "+974" => "Qatar", "+40" => "Romania", "+966" => "Saudi Arabia", "+381" => "Serbia", "+65" => "Singapore", "+421" => "Slovakia", "+386" => "Slovenia", "+27" => "South Africa", "+82" => "South Korea", "+34" => "Spain", "+94" => "Sri Lanka", "+46" => "Sweden", "+41" => "Switzerland", "+963" => "Syria", "+886" => "Taiwan", "+992" => "Tajikistan", "+66" => "Thailand", "+90" => "Turkey", "+993" => "Turkmenistan", "+380" => "Ukraine", "+971" => "United Arab Emirates", "+998" => "Uzbekistan", "+84" => "Vietnam", "+967" => "Yemen", "+263" => "Zimbabwe"];
}

function get_flag_countries()
{
	return  ["+44" => "flags/gb.png", "+1" => "flags/us.png", "+61" => "flags/au.png", "+93" => "flags/af.png", "+355" => "flags/al.png", "+213" => "flags/dz.png", "+376" => "flags/ad.png", "+244" => "flags/ao.png", "+54" => "flags/ar.png", "+374" => "flags/am.png", "+43" => "flags/at.png", "+994" => "flags/az.png", "+973" => "flags/bh.png", "+880" => "flags/bd.png", "+375" => "flags/by.png", "+32" => "flags/be.png", "+975" => "flags/bt.png", "+387" => "flags/ba.png", "+55" => "flags/br.png", "+359" => "flags/bg.png", "+855" => "flags/kh.png", "+237" => "flags/cm.png", "+56" => "flags/cl.png", "+86" => "flags/cn.png", "+57" => "flags/co.png", "+385" => "flags/hr.png", "+357" => "flags/cy.png", "+420" => "flags/cz.png", "+45" => "flags/dk.png", "+20" => "flags/eg.png", "+372" => "flags/ee.png", "+358" => "flags/fi.png", "+33" => "flags/fr.png", "+49" => "flags/de.png", "+30" => "flags/gr.png", "+852" => "flags/hk.png", "+36" => "flags/hu.png", "+354" => "flags/is.png", "+91" => "flags/in.png", "+62" => "flags/id.png", "+98" => "flags/ir.png", "+964" => "flags/iq.png", "+353" => "flags/ie.png", "+972" => "flags/il.png", "+39" => "flags/it.png", "+81" => "flags/jp.png", "+962" => "flags/jo.png", "+7" => "flags/ru.png", "+254" => "flags/ke.png", "+965" => "flags/kw.png", "+996" => "flags/kg.png", "+856" => "flags/la.png", "+371" => "flags/lv.png", "+961" => "flags/lb.png", "+370" => "flags/lt.png", "+352" => "flags/lu.png", "+60" => "flags/my.png", "+960" => "flags/mv.png", "+52" => "flags/mx.png", "+373" => "flags/md.png", "+377" => "flags/mc.png", "+976" => "flags/mn.png", "+212" => "flags/ma.png", "+95" => "flags/mm.png", "+977" => "flags/np.png", "+31" => "flags/nl.png", "+64" => "flags/nz.png", "+234" => "flags/ng.png", "+850" => "flags/kp.png", "+47" => "flags/no.png", "+968" => "flags/om.png", "+92" => "flags/pk.png", "+63" => "flags/ph.png", "+48" => "flags/pl.png", "+351" => "flags/pt.png", "+974" => "flags/qa.png", "+40" => "flags/ro.png", "+966" => "flags/sa.png", "+381" => "flags/rs.png", "+65" => "flags/sg.png", "+421" => "flags/sk.png", "+386" => "flags/si.png", "+27" => "flags/za.png", "+82" => "flags/kr.png", "+34" => "flags/es.png", "+94" => "flags/lk.png", "+46" => "flags/se.png", "+41" => "flags/ch.png", "+963" => "flags/sy.png", "+886" => "flags/tw.png", "+992" => "flags/tj.png", "+66" => "flags/th.png", "+90" => "flags/tr.png", "+993" => "flags/tm.png", "+380" => "flags/ua.png", "+971" => "flags/ae.png", "+998" => "flags/uz.png", "+84" => "flags/vn.png", "+967" => "flags/ye.png", "+263" => "flags/zw.png"];
}

function remove_protected_title($title)
{
	return preg_replace('/^Protected:\s*/i', '', $title);
}

add_filter('protected_title_format', function () {
	return '%s'; // removes "Protected:"
});

if (function_exists('acf_add_options_page')) {

	acf_add_options_page(array(
		'page_title'  => 'Booking Settings',
		'menu_title'  => 'Booking Settings',
		'menu_slug'   => 'booking-settings',
		'capability'  => 'edit_posts',
		'redirect'    => false
	));
}

?>



<?php
// Villa Cards Shortcode(WP Backery)
function villa_cards_shortcode()
{
	ob_start();
?>


	<?php
	$args = array(
		'post_type'      => 'villa-detail',
		'post_status'    => 'publish',
		'posts_per_page' => 3,
		'orderby'        => 'date',
		'order'          => 'DESC',
		'meta_query' => array(
			array(
				'key' => 'villastatus',
				'value' => 'live_offline',
				'compare' => '!='
			)
		),
	);

	$villas = get_posts($args);

	// $villas = get_field('villa', 12);
	if ($villas) {
		$fav_villa = [];
		if (isset($_COOKIE['villa_fav'])) {
			$fav_villa = explode(',', $_COOKIE['villa_fav']);
		}
	?>
		<div class="curated-collections" style="padding: 20px 0 85px;">
			<div class="container">
				<div class="villa-collective-box">
					<div class="row">

						<?php
						foreach ($villas as $villa_key => $villa) {
							$post_id = $villa->ID;
							$propertid = get_field('propertyid', $post_id);
							$s_image = get_the_post_thumbnail_url($post_id);
							$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
							$slider_image = !empty($s_image) ? $s_image : $image_not_found;
							$villa_price = (get_field('ispoaprice', $post_id)) ? 'POA' : get_field('currencysymbol', $post_id) . price_format(get_field('minprice', $post_id)) . ' - ' . price_format(get_field('maxprice', $post_id)) . ' / ' . get_field('pricetype', $post_id);

							$villa_detail_url = get_permalink($post_id);
							$Villa_info_div = get_villa_info_div($post_id);

						?>
							<div class="col-lg-4">
								<div class="villa-collective-sure-box">
									<div class="villa-collective-sure-box-img" style="background-image:url('<?php echo $slider_image; ?>');">
										<div class="villa-collective-info">
											<?php
											$i_class = "fa-regular fa-heart";
											if (in_array($post_id, $fav_villa)) {
												$i_class = "fa fa-heart";
											}
											?>
											<?php echo category_bedge($post_id); ?>
											<span class="add_favourite" data-type="0" data-villa_id="<?php echo $post_id; ?>"><i class="<?php echo $i_class; ?>"></i></span>
										</div>
									</div>
									<?php echo $Villa_info_div; ?>
								</div>
							</div>

						<?php
						}
						?>
					</div>
					<div class="row">
						<div class="col-lg-12 text-center mt-5">
							<a href="javascript:void(0);" class="thm-btn-3">VIEW ALL IONIAN VILLAS</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	<?php
	}
	?>


<?php
	return ob_get_clean();
}
add_shortcode('villa_cards', 'villa_cards_shortcode');
?>

<?php
// Villa Cards Shortcode(WP Backery)
function villa_cards_mallorca_shortcode()
{
	ob_start();
?>


	<?php
	$args = array(
		'post_type'      => 'villa-detail',
		'post_status'    => 'publish',
		'posts_per_page' => 3,
		'orderby'        => 'date',
		'order'          => 'DESC',
		'country'         => 'mallorca',
		'meta_query' => array(
			array(
				'key' => 'villastatus',
				'value' => 'live_offline',
				'compare' => '!='
			)
		),
	);

	$villas = get_posts($args);

	// $villas = get_field('villa', 12);
	if ($villas) {
		$fav_villa = [];
		if (isset($_COOKIE['villa_fav'])) {
			$fav_villa = explode(',', $_COOKIE['villa_fav']);
		}
	?>
		<div class="curated-collections" style="padding: 20px 0 85px;">
			<div class="container">
				<div class="villa-collective-box">
					<div class="row">

						<?php
						foreach ($villas as $villa_key => $villa) {
							$post_id = $villa->ID;
							$propertid = get_field('propertyid', $post_id);
							$s_image = get_the_post_thumbnail_url($post_id);
							$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
							$slider_image = !empty($s_image) ? $s_image : $image_not_found;
							$villa_price = (get_field('ispoaprice', $post_id)) ? 'POA' : get_field('currencysymbol', $post_id) . price_format(get_field('minprice', $post_id)) . ' - ' . price_format(get_field('maxprice', $post_id)) . ' / ' . get_field('pricetype', $post_id);

							$villa_detail_url = get_permalink($post_id);
							$Villa_info_div = get_villa_info_div($post_id);

						?>
							<div class="col-lg-4">
								<div class="villa-collective-sure-box">
									<div class="villa-collective-sure-box-img" style="background-image:url('<?php echo $slider_image; ?>');">
										<div class="villa-collective-info">
											<?php
											$i_class = "fa-regular fa-heart";
											if (in_array($post_id, $fav_villa)) {
												$i_class = "fa fa-heart";
											}
											?>
											<?php echo category_bedge($post_id); ?>
											<span class="add_favourite" data-type="0" data-villa_id="<?php echo $post_id; ?>"><i class="<?php echo $i_class; ?>"></i></span>
										</div>
									</div>
									<?php echo $Villa_info_div; ?>
								</div>
							</div>

						<?php
						}
						?>
					</div>
					<div class="row">
						<div class="col-lg-12 text-center mt-5">
							<a href="<?= site_url(); ?>/mallorca/" class="thm-btn-3">VIEW ALL MALLORCA VILLAS</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	<?php
	}
	?>


<?php
	return ob_get_clean();
}
add_shortcode('villa_mallorca_cards', 'villa_cards_mallorca_shortcode');
?>

<?php
// Villa Cards Shortcode(WP Backery)
function villa_cards_kenyan_coast_shortcode()
{
	ob_start();
?>


	<?php
	$args = array(
		'post_type'      => 'villa-detail',
		'post_status'    => 'publish',
		'posts_per_page' => 3,
		'orderby'        => 'date',
		'order'          => 'DESC',
		'country'         => 'kenya',
		'meta_query' => array(
			array(
				'key' => 'villastatus',
				'value' => 'live_offline',
				'compare' => '!='
			)
		),
	);

	$villas = get_posts($args);

	// $villas = get_field('villa', 12);
	if ($villas) {
		$fav_villa = [];
		if (isset($_COOKIE['villa_fav'])) {
			$fav_villa = explode(',', $_COOKIE['villa_fav']);
		}
	?>
		<div class="curated-collections" style="padding: 20px 0 85px;">
			<div class="container">
				<div class="villa-collective-box">
					<div class="row">

						<?php
						foreach ($villas as $villa_key => $villa) {
							$post_id = $villa->ID;
							$propertid = get_field('propertyid', $post_id);
							$s_image = get_the_post_thumbnail_url($post_id);
							$image_not_found = get_stylesheet_directory_uri() . '/assets/images/no-found.jpg';
							$slider_image = !empty($s_image) ? $s_image : $image_not_found;
							$villa_price = (get_field('ispoaprice', $post_id)) ? 'POA' : get_field('currencysymbol', $post_id) . price_format(get_field('minprice', $post_id)) . ' - ' . price_format(get_field('maxprice', $post_id)) . ' / ' . get_field('pricetype', $post_id);

							$villa_detail_url = get_permalink($post_id);
							$Villa_info_div = get_villa_info_div($post_id);

						?>
							<div class="col-lg-4">
								<div class="villa-collective-sure-box">
									<div class="villa-collective-sure-box-img" style="background-image:url('<?php echo $slider_image; ?>');">
										<div class="villa-collective-info">
											<?php
											$i_class = "fa-regular fa-heart";
											if (in_array($post_id, $fav_villa)) {
												$i_class = "fa fa-heart";
											}
											?>
											<?php echo category_bedge($post_id); ?>
											<span class="add_favourite" data-type="0" data-villa_id="<?php echo $post_id; ?>"><i class="<?php echo $i_class; ?>"></i></span>
										</div>
									</div>
									<?php echo $Villa_info_div; ?>
								</div>
							</div>

						<?php
						}
						?>
					</div>
					<div class="row">
						<div class="col-lg-12 text-center mt-5">
							<a href="<?= site_url(); ?>/kenya" class="thm-btn-3">VIEW ALL KENYA VILLAS</a>
						</div>
					</div>
				</div>
			</div>
		</div>
	<?php
	}
	?>


<?php
	return ob_get_clean();
}
add_shortcode('villa_kenyan_coast_cards', 'villa_cards_kenyan_coast_shortcode');
?>


<?php
// Villa Cards Shortcode(WP Backery)
function journal_2027_curated_collections_shortcode()
{
	ob_start();
?>


	<?php
	$villas = get_field('villa', 60111);
	if ($villas) {
		$fav_villa = [];
		if (isset($_COOKIE['villa_fav'])) {
			$fav_villa = explode(',', $_COOKIE['villa_fav']);
		}
	?>
		<div class="curated-collections" style="padding: 40px 0 85px;">
			<div class="container">
				<div class="row">
					<div class="col-xxl-12">
						<div class="section-head animate__animated animate__slideInUp">
							<span>VILLA COLLECTIVE</span>
							<h2>NOT SURE WHERE TO GO?</h2>
						</div>
					</div>
				</div>
				<div class="villa-collective-box">
					<div class="row">
						<div class="col-xxl-12">
							<div class="villa-collective-sure animate__animated animate__slideInUp villa_collective_div">

								<div class="row">
									<div class="col-xxl-12">
										<div class="carousel-wrap">
											<div class="tab-slider-owl-carousel owl-carousel owl-theme">
												<?php
												foreach ($villas as $villa_key => $villa) {
													$post_id = $villa;
													$propertid = get_field('propertyid', $post_id);
													$s_image = get_the_post_thumbnail_url($post_id);
													$slider_image = !empty($s_image) ? $s_image : $image_not_found;
													$villa_price = (get_field('ispoaprice', $post_id)) ? 'POA' : get_field('currencysymbol', $post_id) . price_format(get_field('minprice', $post_id)) . ' - ' . price_format(get_field('maxprice', $post_id)) . ' / ' . get_field('pricetype', $post_id);

													$villa_detail_url = get_permalink($post_id);
													$Villa_info_div = get_villa_info_div($post_id);

												?>
													<div class="item">
														<div class="villa-collective-sure-box">
															<div class="villa-collective-sure-box-img" data-image="background-image:url('<?php echo $slider_image; ?>');">
																<div class="villa-collective-info">
																	<?php
																	$i_class = "fa-regular fa-heart";
																	if (in_array($post_id, $fav_villa)) {
																		$i_class = "fa fa-heart";
																	}
																	?>
																	<?php echo category_bedge($post_id); ?>
																	<span class="add_favourite" data-type="0" data-villa_id="<?php echo $post_id; ?>"><i class="<?php echo $i_class; ?>"></i></span>
																</div>
															</div>
															<?php echo $Villa_info_div; ?>
														</div>
													</div>
												<?php
												}
												?>
											</div>
										</div>
									</div>
								</div>

							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	<?php
	}
	?>

	<script>
		$(document).ready(function() {
			var _villa_collective_slider = $('.tab-slider-owl-carousel').owlCarousel({
				autoplay: true,
				loop: false,
				margin: 30,
				nav: true,
				lazyLoad: true,
				navText: [
					"<i class='fa-solid fa-angle-left'></i>",
					"<i class='fa-solid fa-angle-right'></i>"
				],
				dots: false,
				mouseDrag: true,
				autoplayTimeout: 4000,
				smartSpeed: 1000,
				responsiveClass: true,
				responsive: {
					0: {
						items: 1
					},
					575: {
						items: 1
					},
					768: {
						items: 2
					},
					992: {
						items: 2
					},
					1000: {
						items: 3
					}
				},
				onInitialized: setimagetoslide,
			});

			function setimagetoslide() {
				setTimeout(function() {
					$.each(_villa_collective_slider.find(".owl-item.active .villa-collective-sure-box-img"), function(index, current) {
						const image = $(current).data('image');
						$(current).attr('style', image);
					});

				}, 100);
			}

			_villa_collective_slider.on('changed.owl.carousel', function(e) {
				setimagetoslide()
			});


			$(".journal-article .vc_single_image-img").each(function() {

				var sizes = $(this).attr('sizes');
				var data_sizes = $(this).attr('data-sizes');

				if (data_sizes == '(max-width: 640px) 100vw, 640px' || data_sizes == '(max-width: 300px) 100vw, 300px') {
					$(this).removeAttr('sizes');
					$(this).removeAttr('data-sizes');
				}
			});
		});
	</script>


<?php
	return ob_get_clean();
}
add_shortcode('journal_2027_curated_collections', 'journal_2027_curated_collections_shortcode');
?>