# Selectorları merkezleştireceğiz
    
SELECTORS = {
    "category": "ul.breadcrumb-list li.product-detail-breadcrumbs-item a::text",
        
    "title": [
        "h1.product-title",  
        "h1[data-testid='product-title']",
        "h1.pr-new-br span.prdct-desc-cntnr-name::text",
        "h1::text"
    ],
        
    "evaluation": [
        "div.envoy div.product-details-other-details div.reviews-summary-rating-detail span.reviews-summary-average-rating::text",
        "div.product-details-other-details div.variant-pdp span.reviews-summary-average-rating::text",
    ],
        
    "evaluation_len": [
        "div.product-details-other-details a.reviews-summary-reviews-detail span.b::text",
        "div.product-details-other-details div.variant-pdp a.reviews-summary-reviews-detail span.b::text",
    ],
        
    "price": [
        "div.prc-box-dsc::text",
        "div.prc-dsc::text",
        "span.prc-slg::text",
        "div.product-price-container span.discounted::text",
        "div.campaign-price-content span::text",
        "div.campaign-price-content p.old-price::text",
        "div.price-wrapper div.price-container span.discounted::text",
        "div.price-wrapper div.ty-plus-price-original-price::text",
        "div.price-wrapper span.discounted::text",
        "div.price-wrapper div.price-view span.original::text",
    ],
        
    "images": "img[data-testid='image']::attr(src)",
        
    "explanation": [
        "div.product-info-content *::text",          # Ürün Bilgileri (Madde madde olan yer)
        "div.content-description-container *::text", # Ürün Açıklaması (Detaylı metin)
        "div.detail-desc-container *::text"          # Eski tip açıklama yapısı
    ]
        
}