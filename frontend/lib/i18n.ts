/**
 * Lightweight i18n for feedback messages.
 *
 * ACC-01: Feedback and instructions available in Telugu, Hindi, and Tamil.
 * The *explanation* is in the student's language; the *practice* stays in English.
 */

export type Locale = "en" | "te" | "hi" | "ta";

const translations: Record<string, Record<Locale, string>> = {
  // Login & Auth
  "auth.welcome": {
    en: "Welcome back",
    te: "తిరిగి స్వాగతం",
    hi: "वापसी पर स्वागत है",
    ta: "மீண்டும் வரவேற்கிறோம்",
  },
  "auth.expired": {
    en: "Your session expired — please sign in again",
    te: "మీ సెషన్ గడువు ముగిసింది — దయచేసి మళ్ళీ సైన్ ఇన్ చేయండి",
    hi: "आपका सत्र समाप्त हो गया — कृपया फिर से साइन इन करें",
    ta: "உங்கள் அமர்வு காலாவதியானது — மீண்டும் உள்நுழைக",
  },
  // Results
  "result.calibrated": {
    en: "Calibrated against human raters",
    te: "మానవ రేటర్లతో క్యాలిబ్రేట్ చేయబడింది",
    hi: "मानव रेटर्स के साथ कैलिब्रेटेड",
    ta: "மனித மதிப்பீட்டாளர்களுடன் தர நிர்ணயம் செய்யப்பட்டது",
  },
  "result.uncalibrated": {
    en: "Not yet checked against human listeners. Useful for tracking your own progress; not a score to quote to anyone.",
    te: "ఇంకా మానవ శ్రోతలతో సరిపోల్చబడలేదు. మీ పురోగతిని ట్రాక్ చేయడానికి ఉపయోగకరం; ఎవరికీ చెప్పడానికి స్కోర్ కాదు.",
    hi: "अभी मानव श्रोताओं से सत्यापित नहीं हुआ। अपनी प्रगति ट्रैक करने के लिए उपयोगी; किसी को बताने के लिए स्कोर नहीं।",
    ta: "இன்னும் மனித கேட்போருடன் சரிபார்க்கப்படவில்லை. உங்கள் முன்னேற்றத்தை கண்காணிக்க பயனுள்ளது; யாருக்கும் சொல்லக்கூடிய மதிப்பெண் அல்ல.",
  },
  "result.not_scored": {
    en: "Not scored",
    te: "స్కోర్ చేయబడలేదు",
    hi: "स्कोर नहीं किया गया",
    ta: "மதிப்பிடப்படவில்லை",
  },
  "result.gap_closing": {
    en: "gap closing",
    te: "గ్యాప్ క్లోజింగ్",
    hi: "अंतर कम करना",
    ta: "இடைவெளியை குறைத்தல்",
  },
  // Actions
  "action.flag_raised": {
    en: "At-risk flag raised",
    te: "అట్-రిస్క్ ఫ్లాగ్ ఎత్తబడింది",
    hi: "जोखिम फ्लैग उठाया गया",
    ta: "ஆபத்து கொடி எழுப்பப்பட்டது",
  },
  "action.flag_resolved": {
    en: "Flag resolved",
    te: "ఫ్లాగ్ పరిష్కరించబడింది",
    hi: "फ्लैग हल किया गया",
    ta: "கொடி தீர்க்கப்பட்டது",
  },
  "action.user_created": {
    en: "User created successfully",
    te: "వినియోగదారుడు విజయవంతంగా సృష్టించబడ్డాడు",
    hi: "उपयोगकर्ता सफलतापूर्वक बनाया गया",
    ta: "பயனர் வெற்றிகரமாக உருவாக்கப்பட்டார்",
  },
  "action.cohort_created": {
    en: "Cohort created",
    te: "కోహోర్ట్ సృష్టించబడింది",
    hi: "समूह बनाया गया",
    ta: "குழு உருவாக்கப்பட்டது",
  },
  "action.profile_published": {
    en: "Assessment profile published",
    te: "అంచనా ప్రొఫైల్ ప్రచురించబడింది",
    hi: "मूल्यांकन प्रोफाइल प्रकाशित",
    ta: "மதிப்பீட்டு சுயவிவரம் வெளியிடப்பட்டது",
  },
  // Practice
  "practice.try_harder": {
    en: "Try a harder challenge next",
    te: "తదుపరి కష్టమైన సవాలు ప్రయత్నించండి",
    hi: "अगली बार कठिन चुनौती आज़माएं",
    ta: "அடுத்து கடினமான சவாலை முயற்சிக்கவும்",
  },
  "practice.weak_area": {
    en: "This is your weakest area — let's target it",
    te: "ఇది మీ బలహీనమైన ప్రాంతం — దీన్ని లక్ష్యంగా చేద్దాం",
    hi: "यह आपका सबसे कमजोर क्षेत्र है — इसे लक्षित करते हैं",
    ta: "இது உங்கள் மிகவும் பலவீனமான பகுதி — இதை இலக்காக்கலாம்",
  },
  // Streaks
  "streak.keep_going": {
    en: "Keep your streak going!",
    te: "మీ స్ట్రీక్ కొనసాగించండి!",
    hi: "अपनी लकीर जारी रखें!",
    ta: "உங்கள் தொடர்ச்சியை தொடருங்கள்!",
  },
  "streak.welcome": {
    en: "Welcome back — your streak is waiting",
    te: "తిరిగి స్వాగతం — మీ స్ట్రీక్ వెయిట్ చేస్తోంది",
    hi: "वापसी पर स्वागत — आपकी लकीर इंतज़ार कर रही है",
    ta: "மீண்டும் வரவேற்கிறோம் — உங்கள் தொடர்ச்சி காத்திருக்கிறது",
  },
  // Time
  "time.minutes_left": {
    en: "minutes left",
    te: "నిమిషాలు మిగిలి ఉన్నాయి",
    hi: "मिनट बाकी",
    ta: "நிமிடங்கள் மீதம்",
  },
  "time.section_complete": {
    en: "Section complete",
    te: "సెక్షన్ పూర్తయింది",
    hi: "अनुभाग पूरा",
    ta: "பிரிவு முடிந்தது",
  },
  // Misc
  "misc.loading": {
    en: "Loading…",
    te: "లోడ్ అవుతోంది…",
    hi: "लोड हो रहा है…",
    ta: "ஏற்றுகிறது…",
  },
  "misc.save": {
    en: "Save",
    te: "సేవ్ చేయండి",
    hi: "सहेजें",
    ta: "சேமி",
  },
  "misc.cancel": {
    en: "Cancel",
    te: "రద్దు",
    hi: "रद्द करें",
    ta: "ரத்துசெய்",
  },
  "misc.confirm": {
    en: "Confirm",
    te: "నిర్ధారించండి",
    hi: "पुष्टि करें",
    ta: "உறுதிசெய்",
  },
};

/** Get a translated string. Falls back to English if no translation exists. */
export function t(key: string, locale: Locale = "en"): string {
  const entry = translations[key];
  if (!entry) return key;
  return entry[locale] ?? entry.en ?? key;
}

/** Detect locale from the user's ui_language setting. */
export function detectLocale(uiLanguage?: string): Locale {
  const map: Record<string, Locale> = {
    en: "en", te: "te", hi: "hi", ta: "ta",
    telugu: "te", hindi: "hi", tamil: "ta",
  };
  return map[(uiLanguage ?? "").toLowerCase()] ?? "en";
}
