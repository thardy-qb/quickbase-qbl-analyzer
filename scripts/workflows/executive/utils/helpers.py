from typing import Any, Dict, Optional


class SafeExtractor:
    """
    Centralized utility for safely extracting values from nested data structures.
    """
    
    @staticmethod
    def get_nested(data: Any, *keys: str, default: Any = "") -> Any:
        """
        Safely navigate nested dictionary/object structures.
        
        Args:
            data: The data structure to navigate
            *keys: Sequence of keys to traverse
            default: Default value if navigation fails
            
        Returns:
            The found value or default
            
        Example:
            SafeExtractor.get_nested(data, "Properties", "Field", "Field", default="")
        """
        current = data
        try:
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key, {})
                elif hasattr(current, key):
                    current = getattr(current, key, {})
                else:
                    return default
                    
                if current is None:
                    return default
            return current if current != {} else default
        except (AttributeError, KeyError, TypeError):
            return default
    
    @staticmethod
    def get_dict(data: Any, *keys: str, default: Optional[Dict] = None) -> Dict:
        """
        Safely extract a dictionary from nested structure.
        """
        if default is None:
            default = {}
        result = SafeExtractor.get_nested(data, *keys, default=default)
        return result if isinstance(result, dict) else default
