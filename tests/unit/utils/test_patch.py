"""
文本文件 patch 逻辑单元测试

测试 whatthepatch 库的 patch 解析与应用，
以及换行符规范化和 SHA-256 哈希计算。
"""
import hashlib

import pytest
import whatthepatch
from whatthepatch.exceptions import HunkApplyException


class TestPatchApply:
    """测试 patch 解析与应用"""

    def test_normal_patch(self) -> None:
        """正常 patch 应用"""
        original = "line1\nline2\nline3"
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+LINE2\n"
            " line3\n"
        )

        diffs = list(whatthepatch.parse_patch(patch_text))
        assert len(diffs) == 1

        result = whatthepatch.apply_diff(diffs[0], original)
        new_text = '\n'.join(result)

        assert "LINE2" in new_text
        assert "line2" not in new_text

    def test_add_lines_patch(self) -> None:
        """添加行的 patch"""
        original = "line1\nline2"
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,2 +1,3 @@\n"
            " line1\n"
            " line2\n"
            "+line3\n"
        )

        diffs = list(whatthepatch.parse_patch(patch_text))
        result = whatthepatch.apply_diff(diffs[0], original)
        new_text = '\n'.join(result)

        assert "line3" in new_text

    def test_delete_lines_patch(self) -> None:
        """删除行的 patch"""
        original = "line1\nline2\nline3"
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,2 @@\n"
            " line1\n"
            "-line2\n"
            " line3\n"
        )

        diffs = list(whatthepatch.parse_patch(patch_text))
        result = whatthepatch.apply_diff(diffs[0], original)
        new_text = '\n'.join(result)

        assert "line2" not in new_text
        assert "line1" in new_text
        assert "line3" in new_text

    def test_invalid_patch_format(self) -> None:
        """无效的 patch 格式返回空列表"""
        diffs = list(whatthepatch.parse_patch("this is not a patch"))
        assert len(diffs) == 0

    def test_patch_context_mismatch(self) -> None:
        """patch 上下文不匹配时抛出异常"""
        original = "line1\nline2\nline3\n"
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-WRONG\n"
            "+REPLACED\n"
            " line3\n"
        )

        diffs = list(whatthepatch.parse_patch(patch_text))
        with pytest.raises(HunkApplyException):
            whatthepatch.apply_diff(diffs[0], original)

    def test_empty_file_patch(self) -> None:
        """空文件应用 patch"""
        original = ""
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -0,0 +1,2 @@\n"
            "+line1\n"
            "+line2\n"
        )

        diffs = list(whatthepatch.parse_patch(patch_text))
        result = whatthepatch.apply_diff(diffs[0], original)
        new_text = '\n'.join(result)

        assert "line1" in new_text
        assert "line2" in new_text


class TestHashComputation:
    """测试 SHA-256 哈希计算"""

    def test_hash_consistency(self) -> None:
        """相同内容产生相同哈希"""
        content = "hello world\n"
        content_bytes = content.encode('utf-8')
        hash1 = hashlib.sha256(content_bytes).hexdigest()
        hash2 = hashlib.sha256(content_bytes).hexdigest()

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_hash_differs_for_different_content(self) -> None:
        """不同内容产生不同哈希"""
        hash1 = hashlib.sha256(b"content A").hexdigest()
        hash2 = hashlib.sha256(b"content B").hexdigest()

        assert hash1 != hash2

    def test_hash_after_normalization(self) -> None:
        """换行符规范化后的哈希一致性"""
        content_crlf = "line1\r\nline2\r\n"
        content_lf = "line1\nline2\n"

        # 规范化后应相同
        normalized = content_crlf.replace('\r\n', '\n').replace('\r', '\n')
        assert normalized == content_lf

        hash_normalized = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        hash_lf = hashlib.sha256(content_lf.encode('utf-8')).hexdigest()

        assert hash_normalized == hash_lf


class TestLineEndingNormalization:
    """测试换行符规范化"""

    def test_crlf_to_lf(self) -> None:
        """CRLF 转换为 LF"""
        content = "line1\r\nline2\r\n"
        normalized = content.replace('\r\n', '\n').replace('\r', '\n')
        assert normalized == "line1\nline2\n"

    def test_cr_to_lf(self) -> None:
        """CR 转换为 LF"""
        content = "line1\rline2\r"
        normalized = content.replace('\r\n', '\n').replace('\r', '\n')
        assert normalized == "line1\nline2\n"

    def test_lf_unchanged(self) -> None:
        """LF 保持不变"""
        content = "line1\nline2\n"
        normalized = content.replace('\r\n', '\n').replace('\r', '\n')
        assert normalized == content

    def test_mixed_line_endings(self) -> None:
        """混合换行符统一为 LF"""
        content = "line1\r\nline2\rline3\n"
        normalized = content.replace('\r\n', '\n').replace('\r', '\n')
        assert normalized == "line1\nline2\nline3\n"
