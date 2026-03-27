import re
import logging
from typing import List
from dojo.models import GeneralSettings
from django.forms import ValidationError

logger = logging.getLogger(__name__)

class CharacterValidation():
    def __call__(self, value):
        if value is None:
            return None

        special_char_regex = GeneralSettings.get_value("REGEX_VALIDATION_NAME", "[<>;&\\(\\)\\{\\};:\\[\\]']") 
        if isinstance(value, List):
            for v in value:
                self.__validation_regex(v, special_char_regex)
        else:
            self.__validation_regex(value, special_char_regex)
        return value  

    def __validation_regex(self, value, special_char_regex):

        if re.search(special_char_regex, value):
            raise ValidationError(f"The name : {value} : cannot contain special characters like < > & ( ) ; : [ ] '")
        return value

valid_chars_validator = CharacterValidation()
